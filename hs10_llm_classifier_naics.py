"""
HS10 Data Center Classification using Claude Tool Calling (Version 2)

This version incorporates NAICS codes and descriptions to provide the LLM
with additional context about the industry classification of each product.

Usage:
    python hs10_llm_classifier_v2.py

Requirements:
    pip install anthropic pandas

You'll need an ANTHROPIC_API_KEY environment variable set.
"""

import anthropic
import pandas as pd
import json
import time
from typing import Optional

# Initialize the client
client = anthropic.Anthropic()

# =============================================================================
# DEFINE THE CLASSIFICATION TOOL
# =============================================================================

CLASSIFICATION_TOOL = {
    "name": "classify_hs10_code",
    "description": "Record the classification of an HS10 commodity code for its relevance to AI data center construction and operation",
    "input_schema": {
        "type": "object",
        "properties": {
            "relevance": {
                "type": "string",
                "enum": ["High", "Medium", "Low"],
                "description": "How relevant is this product to AI data center construction or operation. High = directly used in data centers, Medium = sometimes used or indirect input, Low = not relevant"
            },
            "confidence": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Confidence in this assessment from 0 to 100"
            },
            "primary_category": {
                "type": "string",
                "enum": [
                    "Compute_Hardware",
                    "Networking_Telecom",
                    "Cooling_HVAC", 
                    "Electrical_Power",
                    "Building_Structure",
                    "Fire_Safety_Security",
                    "Specialty_Materials",
                    "Maintenance_Operations",
                    "Not_DC_Related"
                ],
                "description": "Primary use category for this product"
            },
            "specific_use": {
                "type": "string",
                "description": "Specific application in a data center context (e.g., 'GPU accelerators', 'backup generator fuel', 'server rack cooling')"
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of why this classification was chosen"
            }
        },
        "required": ["relevance", "confidence", "primary_category", "specific_use", "reasoning"]
    }
}

SYSTEM_PROMPT = """You are an expert in AI data center construction, operations, and supply chains. 

Your task is to classify products by their relevance to building and operating AI-focused data centers (hyperscale facilities running GPU clusters for training and inference).

You will be provided with two pieces of information about each product:

1. **HS10 Code and Description**: The Harmonized System (HS) is an international product classification used for trade statistics. The HS10 code is a 10-digit code used by U.S. Customs to classify imported goods. The description tells you what the physical product is.

2. **NAICS Code and Description**: The North American Industry Classification System (NAICS) indicates which U.S. industry produces or uses this product. This provides additional context about the product's typical industrial application.

Consider these categories of relevant products:
- COMPUTE: GPUs, CPUs, memory, PCBs, servers, storage drives, semiconductors
- NETWORKING: Fiber optics, switches, routers, transceivers, cables
- COOLING: Chillers, cooling towers, CRAH units, fans, pumps, refrigerants, glycol
- ELECTRICAL: Transformers, switchgear, UPS, batteries, generators, cables, busbars
- BUILDING: Structural steel, concrete, rebar, insulation, raised floors, fire suppression
- SPECIALTY MATERIALS: Rare earths, copper, aluminum, tantalum, thermal interface materials

Be thoughtful about edge cases:
- "Diesel engines" could be for generators (relevant) or vehicles (not relevant) - use NAICS to help disambiguate
- "Pumps" could be for cooling systems (relevant) or unrelated industrial use
- "Copper wire" is relevant for electrical systems
- Food, textiles, furniture, and consumer goods are generally NOT relevant
- The NAICS description can help clarify ambiguous HS descriptions

Use the classify_hs10_code tool to record your assessment."""


def classify_single_code(hs10_code: str, description: str, 
                         naics_code: str = None, naics_description: str = None) -> dict:
    """
    Classify a single HS10 code using Claude with tool calling.
    
    Parameters
    ----------
    hs10_code : str
        The 10-digit HS code
    description : str
        The commodity description
    naics_code : str, optional
        The associated NAICS code
    naics_description : str, optional
        The NAICS industry description
        
    Returns
    -------
    dict
        Classification result with relevance, confidence, category, etc.
    """
    
    # Build the user message with both HS and NAICS info
    user_content = f"""Classify this product:

HS10 Code: {hs10_code}
HS Description: {description}"""
    
    if naics_code and naics_description:
        user_content += f"""

NAICS Code: {naics_code}
NAICS Industry: {naics_description}"""
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=400,
        system=SYSTEM_PROMPT,
        tools=[CLASSIFICATION_TOOL],
        tool_choice={"type": "tool", "name": "classify_hs10_code"},
        messages=[{
            "role": "user", 
            "content": user_content
        }]
    )
    
    # Extract the tool call result
    tool_use_block = response.content[0]
    
    # The 'input' field contains our structured data
    result = tool_use_block.input
    
    # Add metadata
    result['hs10_code'] = hs10_code
    result['description'] = description
    result['naics_code'] = naics_code
    result['naics_description'] = naics_description
    
    return result


def classify_batch(codes_df: pd.DataFrame, 
                   delay: float = 0.5,
                   checkpoint_file: Optional[str] = None,
                   hs_col: str = 'HS10',
                   desc_col: str = 'long_desc',
                   naics_col: str = 'naics',
                   naics_desc_col: str = 'naics_descriptions') -> pd.DataFrame:
    """
    Classify multiple HS10 codes with rate limiting.
    
    Parameters
    ----------
    codes_df : pd.DataFrame
        DataFrame with HS10 codes and descriptions
    delay : float
        Seconds to wait between API calls
    checkpoint_file : str, optional
        Save progress to this file periodically
    hs_col : str
        Column name for HS10 codes
    desc_col : str
        Column name for HS descriptions
    naics_col : str
        Column name for NAICS codes
    naics_desc_col : str
        Column name for NAICS descriptions
        
    Returns
    -------
    pd.DataFrame
        Classification results
    """
    results = []
    total = len(codes_df)
    
    for i, row in codes_df.iterrows():
        code = str(row[hs_col])
        desc = str(row[desc_col])
        naics = str(row.get(naics_col, '')) if pd.notna(row.get(naics_col)) else None
        naics_desc = str(row.get(naics_desc_col, '')) if pd.notna(row.get(naics_desc_col)) else None
        
        try:
            result = classify_single_code(code, desc, naics, naics_desc)
            results.append(result)
            
            print(f"[{len(results)}/{total}] {code}: {result['relevance']} "
                  f"({result['confidence']}%) - {result['primary_category']}")
            
            # Checkpoint every 10 items
            if checkpoint_file and len(results) % 10 == 0:
                pd.DataFrame(results).to_csv(checkpoint_file, index=False)
            
            # Rate limiting
            time.sleep(delay)
            
        except Exception as e:
            print(f"[{len(results)+1}/{total}] ERROR on {code}: {e}")
            results.append({
                'hs10_code': code,
                'description': desc,
                'naics_code': naics,
                'naics_description': naics_desc,
                'relevance': 'Error',
                'confidence': 0,
                'primary_category': 'Error',
                'specific_use': '',
                'reasoning': str(e)
            })
    
    return pd.DataFrame(results)


def resume_batch_classification(
    all_codes_file: str,
    checkpoint_file: str,
    hs_col: str = 'HS10',
    desc_col: str = 'long_desc',
    naics_col: str = 'naics',
    naics_desc_col: str = 'naics_descriptions',
    output_file: Optional[str] = None,
    delay: float = 0.5
) -> pd.DataFrame:
    """
    Resume batch classification by skipping already-processed codes.
    Handles crashes gracefully by reading from checkpoint file.
    
    Parameters
    ----------
    all_codes_file : str
        CSV file with all HS10 codes to classify
    checkpoint_file : str
        CSV file with partially completed results (will be created if doesn't exist)
    hs_col : str
        Column name for HS10 codes (default: 'HS10')
    desc_col : str
        Column name for descriptions (default: 'long_desc')
    naics_col : str
        Column name for NAICS codes (default: 'naics')
    naics_desc_col : str
        Column name for NAICS descriptions (default: 'naics_descriptions')
    output_file : str, optional
        Final output file (default: same as checkpoint_file)
    delay : float
        Seconds between API calls (default: 0.5)
    
    Returns
    -------
    pd.DataFrame
        Combined results (old + new)
        
    Example
    -------
    >>> results = resume_batch_classification(
    ...     all_codes_file='data-input/unique_hs10_naics_descriptions.csv',
    ...     checkpoint_file='hs10_classification_progress_v2.csv',
    ...     output_file='hs10_classification_final_v2.csv'
    ... )
    """
    import os
    
    if output_file is None:
        output_file = checkpoint_file
    
    # Load all codes
    print(f"Loading all codes from: {all_codes_file}")
    all_codes_df = pd.read_csv(all_codes_file)
    print(f"Total codes to classify: {len(all_codes_df):,}")
    
    # Check if checkpoint exists
    if os.path.exists(checkpoint_file):
        print(f"\nFound checkpoint file: {checkpoint_file}")
        completed_df = pd.read_csv(checkpoint_file)
        print(f"Total rows in checkpoint: {len(completed_df):,} codes")
        
        # Filter out error rows - these should be retried
        error_rows = completed_df[completed_df['relevance'] == 'Error']
        success_rows = completed_df[completed_df['relevance'] != 'Error']
        
        if len(error_rows) > 0:
            print(f"Found {len(error_rows):,} error rows (will be retried)")
        print(f"Successfully completed: {len(success_rows):,} codes")
        
        # Only skip successfully completed codes
        completed_codes = set(success_rows['hs10_code'].astype(str))
        remaining_df = all_codes_df[~all_codes_df[hs_col].astype(str).isin(completed_codes)]
        print(f"Remaining to classify: {len(remaining_df):,} codes")
        
        # Keep only successful results for final output
        completed_df = success_rows
    else:
        print(f"\nNo checkpoint file found. Starting fresh.")
        remaining_df = all_codes_df
        completed_df = pd.DataFrame()
    
    # If nothing left to do
    if len(remaining_df) == 0:
        print("\n✅ All codes already classified!")
        return completed_df
    
    print(f"\n🚀 Starting classification of {len(remaining_df):,} remaining codes...")
    print(f"Progress will be saved to: {checkpoint_file}")
    
    # Classify remaining codes
    new_results_df = classify_batch(
        remaining_df,
        delay=delay,
        checkpoint_file=checkpoint_file,
        hs_col=hs_col,
        desc_col=desc_col,
        naics_col=naics_col,
        naics_desc_col=naics_desc_col
    )
    
    # Combine with previous results
    if len(completed_df) > 0:
        final_df = pd.concat([completed_df, new_results_df], ignore_index=True)
    else:
        final_df = new_results_df
    
    # Save final results
    final_df.to_csv(output_file, index=False)
    print(f"\n✅ Complete! Final results saved to: {output_file}")
    print(f"Total classified: {len(final_df):,} codes")
    
    return final_df


# =============================================================================
# DEMO: TEST WITH SAMPLE CODES
# =============================================================================

if __name__ == "__main__":
    
    # Sample HS10 codes to test - with NAICS info
    test_cases = [
        # Clearly relevant
        {
            "hs10": "8542310040",
            "desc": "PROCESSORS (INCLUDING MICROPROCESSORS): GRAPHICS PROCESSING UNITS (GPUS)",
            "naics": "334413",
            "naics_desc": "SEMICONDUCTOR AND RELATED DEVICE MANUFACTURING"
        },
        {
            "hs10": "8471500000",
            "desc": "PROCESSING UNITS FOR AUTOMATIC DATA PROCESSING MACHINES",
            "naics": "334111",
            "naics_desc": "ELECTRONIC COMPUTER MANUFACTURING"
        },
        {
            "hs10": "8544700000",
            "desc": "INSULATED OPTICAL FIBER CABLES WITH INDIVIDUALLY SHEATHED FIBERS",
            "naics": "335921",
            "naics_desc": "FIBER OPTIC CABLE MANUFACTURING"
        },
        # Ambiguous - NAICS helps
        {
            "hs10": "8408909030",
            "desc": "COMPRESSION-IGNITION INTERNAL COMBUSTION PISTON ENGINES, NESOI, EXCEEDING 373 KW",
            "naics": "333618",
            "naics_desc": "OTHER ENGINE EQUIPMENT MANUFACTURING"
        },
        {
            "hs10": "8413702015",
            "desc": "CENTRIFUGAL PUMPS FOR LIQUIDS, SINGLE-STAGE, DISCHARGE OUTLET 5.08 CM OR OVER",
            "naics": "333914",
            "naics_desc": "MEASURING, DISPENSING, AND OTHER PUMPING EQUIPMENT MANUFACTURING"
        },
        # Clearly NOT relevant
        {
            "hs10": "0201200200",
            "desc": "BEEF WITH BONE IN, HIGH-QUALITY CUTS, PROCESSED, FRESH OR CHILLED",
            "naics": "311612",
            "naics_desc": "MEAT PROCESSED FROM CARCASSES"
        },
        {
            "hs10": "6110201075",
            "desc": "SWEATERS, PULLOVERS AND SIMILAR ARTICLES, KNITTED, OF COTTON",
            "naics": "315190",
            "naics_desc": "OTHER APPAREL KNITTING MILLS"
        },
    ]
    
    print("=" * 80)
    print("HS10 CLASSIFICATION DEMO WITH NAICS CONTEXT")
    print("=" * 80)
    print()
    print(f"Testing {len(test_cases)} sample codes...")
    print()
    
    # Classify each test case
    results = []
    for case in test_cases:
        print("-" * 60)
        print(f"HS10:  {case['hs10']}")
        print(f"Desc:  {case['desc'][:60]}...")
        print(f"NAICS: {case['naics']} - {case['naics_desc']}")
        
        try:
            result = classify_single_code(
                case['hs10'], 
                case['desc'],
                case['naics'],
                case['naics_desc']
            )
            results.append(result)
            
            print(f"\n  RELEVANCE:  {result['relevance']}")
            print(f"  CONFIDENCE: {result['confidence']}%")
            print(f"  CATEGORY:   {result['primary_category']}")
            print(f"  USE:        {result['specific_use']}")
            print(f"  REASONING:  {result['reasoning']}")
            
        except Exception as e:
            print(f"\n  ERROR: {e}")
            
        print()
        time.sleep(0.5)  # Rate limiting
    
    # Create summary DataFrame
    df = pd.DataFrame(results)
    
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    print("Results by Relevance:")
    print(df['relevance'].value_counts().to_string())
    print()
    print("Results by Category:")
    print(df['primary_category'].value_counts().to_string())
    
    # Save results
    output_file = "llm_classification_demo_results_v2.csv"
    df.to_csv(output_file, index=False)
    print(f"\nResults saved to: {output_file}")
