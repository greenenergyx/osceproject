def generate_osce(title, system, model, api_v, difficulty):
    url = f"https://generativelanguage.googleapis.com/{api_v}/models/{model}:generateContent?key={GEMINI_KEY}"
    
    # --- STEP 1: INITIAL DRAFT ---
    draft_prompt = f"""
    Draft a Radiology OSCE case for: {title} ({system}).
    Follow the Radiopaedia Abdominal style.
    Include Clinical History, 5 Questions, and a detailed Marking Guide with [0.5/1.0] point allocations.
    """
    
    try:
        # Get Draft
        payload = {"contents": [{"parts": [{"text": draft_prompt}]}]}
        res = requests.post(url, json=payload, timeout=20).json()
        draft_text = res['candidates'][0]['content']['parts'][0]['text']

        # --- STEP 2: CLINICAL AUDIT ---
        # We use a second prompt to "Critique" the draft for hallucinations
        audit_prompt = f"""
        You are a Senior Radiology Lead. Audit this OSCE case for factual accuracy.
        CHECK SPECIFICALLY:
        - MRI/CT signal characteristics (e.g., Fat must be T1 hyperintense).
        - Anatomical correctness.
        - Clinical plausibility.
        
        CASE TO AUDIT:
        {draft_text}
        
        OUTPUT FORMAT:
        RATING: [1-10]
        ERRORS FOUND: [List errors or 'None']
        CORRECTED CASE: [Provide the full rewritten case here]
        """
        
        audit_payload = {"contents": [{"parts": [{"text": audit_prompt}]}]}
        audit_res = requests.post(url, json=audit_payload, timeout=20).json()
        audit_output = audit_res['candidates'][0]['content']['parts'][0]['text']

        # --- STEP 3: PARSING THE RESULTS ---
        # We split the audit output to show you the "Quality Control" report
        return audit_output

    except Exception as e:
        return f"⚠️ Error in Multi-Step Generation: {str(e)}"
