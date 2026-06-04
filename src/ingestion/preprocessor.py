"""
Text Preprocessor — Cleans and classifies extracted text
=========================================================

WHAT THIS MODULE DOES:
    Takes raw extracted text → Returns clean, classified text.

    Three responsibilities:
    1. CLEAN: Remove boilerplate, normalize whitespace
    2. CLASSIFY: Detect what type of architecture content this is
    3. FILTER: Skip meaningless slides (too short, just headers)

WHY THIS IS CRITICAL:
    Look at what the extractor produced for your DataStories PPT:

    BEFORE preprocessing:
        title = "Copyright © 2025 Accenture. All rights reserved."
        content = "Copyright © 2025 Accenture. All rights reserved.
                   Hosting Integration – Considerations..."

    AFTER preprocessing:
        title = "Hosting Integration – Considerations"
        content = "Hosting Integration – Considerations..."
        section_type = "hosting"

    The embedding model converts text to vectors based on MEANING.
    If your chunk contains "Copyright © 2025 Accenture" — that text
    has a MEANING (legal, copyright) that COMPETES with the actual
    architecture content during retrieval.

    Result: "Explain hosting" might retrieve a copyright-heavy chunk
    instead of the actual hosting content.

RAG CONCEPT — Data Quality:
    This is the #1 lesson from the RAG iceberg:
    GARBAGE IN → GARBAGE OUT

    No amount of fancy retrieval or powerful LLMs can fix bad data.
    The preprocessor is your DATA QUALITY layer.

PYTHON CONCEPTS COVERED:
    - Regular expressions (re module) — pattern matching
    - re.sub() — find and replace with patterns
    - re.IGNORECASE, re.MULTILINE — regex flags
    - String methods: .lower(), .split(), .strip()
    - Early return pattern

C# EQUIVALENTS:
    - re.sub(pattern, replacement, text) → Regex.Replace(text, pattern, replacement)
    - re.search(pattern, text) → Regex.IsMatch(text, pattern)
    - re.IGNORECASE → RegexOptions.IgnoreCase
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TextPreprocessor:
    """
    Cleans, classifies, and filters extracted text.

    Used by the chunker BEFORE creating chunks.
    Every chunk that enters the vector database has been through this.
    """

    # ── Boilerplate Patterns ──────────────────────────────────
    #
    # PYTHON CONCEPT — Raw strings (r"..."):
    #   Regular expressions use backslashes a lot: \s, \d, \n
    #   In normal strings, \ is an escape character: "\n" = newline
    #   In raw strings, \ is literal: r"\n" = backslash + n
    #
    #   ALWAYS use raw strings for regex patterns.
    #   C# equivalent: @"\s+" (verbatim string literal)
    #
    # PYTHON CONCEPT — Regular expressions:
    #   \s+     → one or more whitespace characters
    #   \d{4}   → exactly 4 digits (matches "2025")
    #   \.      → literal dot (. alone means "any character")
    #   .*?     → any characters, non-greedy (as few as possible)
    #   ^       → start of line (with MULTILINE flag)
    #   $       → end of line (with MULTILINE flag)
    #
    #   C# equivalent:
    #       new Regex(@"Copyright\s*©\s*\d{4}", RegexOptions.IgnoreCase)

    BOILERPLATE_PATTERNS = [
        # ── Accenture-specific boilerplate ──
        # Matches: "Copyright © 2025 Accenture. All rights reserved."
        # Also matches variations with extra spaces or missing dot
        r"Copyright\s*©?\s*\d{4}\s*Accenture\.?\s*All\s*rights\s*reserved\.?",

        # Matches: "HIGHLY CONFIDENTIAL- FOR COMPANY INTERNAL USE..."
        r"HIGHLY\s*CONFIDENTIAL.*?ONLY",

        # ── PPT template placeholders ──
        # These leak through from the slide master/layout templates
        r"Place\s+headline\s+here.*?(?:\n|$)",
        r"First\s+level\s+\(bullet\s+\d+pt\)",
        r"Second\s+level\s+\(bullet\s+\d+pt\)",
        r"Third\s+level\s+\(bullet\s+\d+pt\)",
        r"Fourth\s+level\s+\(bullet\s+\d+pt\)",
        r"Fifth\s+level\s+\(bullet\s+\d+pt\)",
        r"Sixth\s+level\s+\(copy\s+\d+pt\)",
        r"Seventh\s+level\s+\(small\s+copy\s+\d+pt\)",
        r"EIGHT\s+LEVEL\s+\(DESCRIPTOR\s+\d+PT\)",
        r"Ninth\s+level\s+\(footer\s+\d+pt\)",

        # Matches: "Ensure the titles are not duplicated..."
        r"Ensure\s+the\s+titles\s*\n?\s*are\s+not\s+duplicated.*?(?:\n|$)",
        r"Please\s+check\s+the\s+set\s+of\s+best\s+practices.*?(?:\n|$)",
        r"Go\s+to\s+Brand\s+Space\s+for\s+more\s+cover\s+options.*?(?:\n|$)",

        # ── Generic PPT placeholders ──
        r"Click\s+to\s+add\s+(?:text|title|subtitle|notes)",
        r"Insert\s+your\s+text\s+here",

        # ── Standalone page/slide numbers ──
        # Matches lines that are ONLY a number (like "5", "20")
        # ^ = start of line, $ = end of line (with MULTILINE)
        r"^\s*\d{1,3}\s*$",
    ]

    # ── Section Type Keywords ─────────────────────────────────
    #
    # This is a KEYWORD-BASED CLASSIFIER.
    # It maps text content to architecture document section types.
    #
    # WHY keyword-based (not ML-based)?
    #   1. Simple, fast, no model needed
    #   2. Fully transparent — you can see WHY it classified something
    #   3. Easy to customize — add your team's terminology
    #   4. Good enough for structured PPTs (headings are descriptive)
    #
    # In Phase 2, you could replace this with:
    #   - Azure AI Language custom classifier
    #   - Few-shot LLM classification
    #   - Fine-tuned text classifier
    #
    # ORDER MATTERS — first match wins.
    # Put MORE SPECIFIC patterns BEFORE general ones.
    # Example: "existing hosting" (current_architecture) must come
    # before "hosting" (hosting) or everything matches "hosting".
    #
    # Each entry: (list_of_keywords, section_type_label)

    SECTION_KEYWORDS = [
        # ══════════════════════════════════════════════════════
        # PRIORITY ORDER MATTERS — first match wins!
        #
        # RULE: More SPECIFIC categories come BEFORE general ones.
        #
        # Problem example:
        #   "Hosting IT Integration Budget Details"
        #   Contains: "integration" AND "budget"
        #   If integration is checked first → tagged "integration" ❌
        #   If budget is checked first → tagged "budget" ✅
        #
        # So: budget, risk, assumptions → BEFORE → integration, hosting
        # ══════════════════════════════════════════════════════

        # ── 1. Current / Existing architecture ──
        # MOST SPECIFIC: "existing hosting" is about current state, not general hosting
        (
            ["current architecture", "existing hosting", "existing infrastructure",
             "existing design", "legacy", "old architecture", "as-is",
             "current state", "existing hosting - overview"],
            "current_architecture"
        ),

        # ── 2. Proposed / Target architecture ──
        (
            ["proposed", "target reference", "reference architecture",
             "to-be", "future state", "new design", "target architecture",
             "target design", "improved", "recommended"],
            "proposed_architecture"
        ),

        # ── 3. Success Criteria ──
        (
            ["success criteria", "acceptance criteria",
             "definition of done", "deemed successful"],
            "success_criteria"
        ),

        # ── 4. Budget / Costs — BEFORE integration! ──
        # "Hosting IT Integration Budget Details" → intent is BUDGET
        (
            ["budget", "cost", "pricing", "expenditure", "estimate",
             "spend", "financial", "opex", "capex", "usd",
             "budget details", "cost breakdown"],
            "budget"
        ),

        # ── 5. Risk & Dependencies — BEFORE integration! ──
        # "Hosting Integration - Risk and Dependencies" → intent is RISK
        (
            ["risk", "dependency", "dependencies", "blocker",
             "concern", "issue", "mitigation"],
            "risk_dependency"
        ),

        # ── 6. Assumptions — BEFORE integration! ──
        # "Key Assumptions" should not be caught by "hosting" or "integration"
        (
            ["assumption", "assumptions", "assumed", "prerequisite"],
            "assumptions"
        ),

        # ── 7. Inventory / Assessment — BEFORE hosting! ──
        # "Inventory and Assessment Summary" → intent is INVENTORY, not hosting
        (
            ["inventory", "assessment", "server list", "disposition",
             "catalog", "resource list"],
            "inventory"
        ),

        # ── 8. Timeline / Milestones ──
        (
            ["milestone", "timeline", "schedule", "gantt",
             "phase", "deadline", "target date", "close +"],
            "timeline"
        ),

        # ── 9. Operations / Support ──
        (
            ["support matrix", "operations support", "raci",
             "escalation", "supporting team"],
            "operations"
        ),

        # ── 10. Contacts ──
        (
            ["contacts", "workstream", "owner", "@accenture.com",
             "@company.com"],
            "contacts"
        ),

        # ── 11. Out of Scope ──
        (
            ["out of scope", "exclusion", "not included"],
            "out_of_scope"
        ),

        # ── 12. Security ──
        # Fairly specific — VPN, firewall, encryption are clear signals
        (
            ["security", "authentication", "auth", "identity", "sso",
             "vpn", "firewall", "access control", "rbac", "encryption",
             "policy 56", "soc", "fasm", "compliance"],
            "security"
        ),

        # ── 13. Migration ──
        (
            ["migration", "migrate", "decommission", "website migration",
             "transition", "cutover", "move to"],
            "migration"
        ),

        # ── 14. Integration — GENERAL CATCH-ALL ──
        # This comes LATE because "integration" appears in MANY slide titles:
        #   "Hosting IT Integration Budget Details" → budget (caught above ✅)
        #   "Hosting Integration - Risk and Dependencies" → risk (caught above ✅)
        #   "Hosting Integration Considerations" → NOW correctly falls here
        (
            ["integration", "api flow", "middleware", "data flow",
             "system integration", "interface", "endpoint"],
            "integration"
        ),

        # ── 15. Hosting / Infrastructure — MOST GENERAL ──
        # This comes LAST of the specific types because "hosting" appears
        # in almost every DataStories slide title.
        # Only content that doesn't match anything above gets tagged "hosting"
        (
            ["hosting", "infrastructure", "environment", "cloud",
             "on-prem", "on-premises", "aws", "azure", "server",
             "compute", "storage", "vm", "virtual machine", "gmcs",
             "landing zone"],
            "hosting"
        ),
    ]

    def clean_text(self, text: str) -> str:
        """
        Remove boilerplate and normalize whitespace.

        WHAT GETS REMOVED (from your DataStories PPT):
            ✂ "Copyright © 2025 Accenture. All rights reserved."
            ✂ "HIGHLY CONFIDENTIAL- FOR COMPANY INTERNAL USE..."
            ✂ "Place headline here (36pt, min 30pt)"
            ✂ "First level (bullet 20pt)"
            ✂ "Ensure the titles are not duplicated..."
            ✂ Standalone numbers like "5", "6", "20" (slide numbers)

        WHAT STAYS:
            ✅ "DataStories has one AWS account"
            ✅ "Hosting Integration Overview"
            ✅ Table data
            ✅ Architecture descriptions

        PYTHON CONCEPT — re.sub(pattern, replacement, text, flags):
            This is regex find-and-replace.
            re.sub(r"Copyright.*?reserved", "", text)
            → Finds "Copyright...reserved" and replaces with ""

            flags=re.IGNORECASE → match regardless of case
            flags=re.MULTILINE → ^ and $ match line start/end (not just string start/end)

            C# equivalent:
                Regex.Replace(text, @"Copyright.*?reserved", "",
                    RegexOptions.IgnoreCase | RegexOptions.Multiline);

        Args:
            text: Raw extracted text (may contain boilerplate)

        Returns:
            Cleaned text with boilerplate removed
        """
        if not text:
            return ""

        cleaned = text

        # Apply each boilerplate pattern
        for pattern in self.BOILERPLATE_PATTERNS:
            cleaned = re.sub(
                pattern,
                "",                               # Replace with empty string
                cleaned,
                flags=re.IGNORECASE | re.MULTILINE  # Case-insensitive + multiline
            )

        # ── Normalize whitespace ──

        # Replace multiple spaces/tabs with single space
        # "Hello     World" → "Hello World"
        cleaned = re.sub(r"[ \t]+", " ", cleaned)

        # Replace 3+ consecutive newlines with just 2
        # Preserves paragraph breaks but removes excessive gaps
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

        # Strip whitespace from each line
        # PYTHON CONCEPT — List comprehension with join:
        #   lines = [line.strip() for line in text.split("\n")]
        #   This creates a NEW list where each line is stripped.
        #
        #   C# equivalent (LINQ):
        #       var lines = text.Split('\n').Select(l => l.Trim());
        #       var cleaned = string.Join("\n", lines);
        lines = [line.strip() for line in cleaned.split("\n")]
        cleaned = "\n".join(lines)

        # Remove leading/trailing whitespace from the entire string
        cleaned = cleaned.strip()

        return cleaned

    def detect_section_type(self, text: str, title: str = "") -> str:
        """
        Detect what type of architecture content this text represents.

        WHY THIS MATTERS FOR YOUR USE CASE:
            When someone asks "Compare current vs proposed for DataStories":

            Without section_type:
                Retriever returns random mix of slides
                LLM gets confused, produces bad comparison

            With section_type:
                Retriever fetches: section_type="current_architecture" chunks
                Retriever fetches: section_type="proposed_architecture" chunks
                LLM gets clean separated context → great comparison

        ALGORITHM:
            1. Combine title + text (title checked first — more reliable)
            2. Convert to lowercase for case-insensitive matching
            3. Check each keyword group in order (first match wins)
            4. Return the section type label

        EXAMPLE with your DataStories PPT:
            Slide 9:  title="Existing Hosting - Overview"
                      → matches "existing hosting" → "current_architecture" ✅

            Slide 11: title="Reference Architecture"
                      → matches "reference architecture" → "proposed_architecture" ✅

            Slide 13: content="Budget Details...costs in USD"
                      → matches "budget" → "budget" ✅

            Slide 18: content="Risk and Dependencies"
                      → matches "risk" → "risk_dependency" ✅

        Args:
            text: The chunk/slide text content
            title: The slide title (checked with higher priority)

        Returns:
            Section type string (e.g., "hosting", "budget", "security")
        """
        # Combine title and text for matching
        # Title gets priority because slide titles are usually
        # more descriptive than body text
        combined = f"{title} {text}".lower()

        for keywords, section_type in self.SECTION_KEYWORDS:
            for keyword in keywords:
                if keyword in combined:
                    logger.debug(
                        f"  Section type: {section_type} "
                        f"(matched: \"{keyword}\")"
                    )
                    return section_type

        return "general"

    def is_meaningful(self, text: str) -> bool:
        """
        Check if text has enough content to be worth embedding.

        WHY THIS MATTERS:
            From your DataStories PPT extraction:

            Slide 6:  32 chars → "Hosting Integration Milestones"
            Slide 7:  35 chars → "Hosting – High Level Migration Plan"
            Slide 23: 59 chars → "Copyright... References"

            These slides have NO useful content — just headings or
            empty section dividers. Embedding them would:
            1. Waste Azure OpenAI API calls (costs money)
            2. Add noise to the vector index
            3. Compete with real content during retrieval

            The is_meaningful check FILTERS THESE OUT.

        RULES:
            ❌ Empty text → not meaningful
            ❌ Less than 50 chars of actual content → not meaningful
            ❌ Single short line (just a header) → not meaningful
            ✅ Multiple lines with 50+ chars → meaningful

        Args:
            text: Cleaned text content

        Returns:
            True if text is worth embedding, False otherwise
        """
        if not text:
            return False

        # Remove all whitespace and check raw character count
        # PYTHON CONCEPT — re.sub(r"\s+", "", text):
        #   Removes ALL whitespace (spaces, tabs, newlines)
        #   to get the "real" content length
        stripped = re.sub(r"\s+", "", text)

        if len(stripped) < 50:
            logger.debug(f"  Not meaningful: only {len(stripped)} chars of content")
            return False

        # Check if it's just a single short line (header/title only)
        # "Hosting Integration Plans" = not useful as a standalone chunk
        # But "Hosting Integration Plans\nThe system uses AWS..." = useful
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if len(lines) <= 1 and len(stripped) < 80:
            logger.debug(f"  Not meaningful: single short line ({len(stripped)} chars)")
            return False

        return True

    def clean_title(self, title: str) -> str:
        """
        Clean a slide title specifically.

        From your DataStories PPT, many titles are:
            "Copyright © 2025 Accenture. All rights reserved."

        This method removes boilerplate from titles AND handles
        the case where the "title" is actually just a page number.

        Args:
            title: Raw title from the extractor

        Returns:
            Cleaned title, or empty string if it was all boilerplate
        """
        if not title:
            return ""

        cleaned = self.clean_text(title)

        # If the cleaned title is just a number, it's a slide number
        # not a real title
        if cleaned.strip().isdigit():
            return ""

        # If the title is too short after cleaning (< 3 chars),
        # it's probably not useful
        if len(cleaned.strip()) < 3:
            return ""

        return cleaned.strip()


# ── Standalone Testing ─────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Add project root to path so we can import extractor
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from src.ingestion.extractor import TextExtractor

    print("=" * 60)
    print("Preprocessor — Standalone Test")
    print("=" * 60)

    # Extract slides first
    test_file = "data/documents/DataStories/Datastories Hosting Integration Blueprint v1.0.pptx"
    if not Path(test_file).exists():
        print(f"\n❌ File not found: {test_file}")
        sys.exit(1)

    extractor = TextExtractor()
    slides = extractor.extract(test_file)

    preprocessor = TextPreprocessor()

    print(f"\nProcessing {len(slides)} extracted slides...\n")

    meaningful_count = 0
    skipped_count = 0

    for slide in slides:
        # Clean the content
        cleaned_content = preprocessor.clean_text(slide.content)
        cleaned_title = preprocessor.clean_title(slide.title)

        # Check if meaningful
        meaningful = preprocessor.is_meaningful(cleaned_content)

        # Detect section type
        section_type = preprocessor.detect_section_type(
            cleaned_content, cleaned_title
        )

        if meaningful:
            meaningful_count += 1
            print(f"  ✅ Slide {slide.slide_number}:")
            print(f"     Title:   {cleaned_title or '(none)'}")
            print(f"     Type:    {section_type}")
            print(f"     Length:  {len(cleaned_content)} chars")
            preview = cleaned_content[:120].replace('\n', ' ')
            print(f"     Preview: {preview}...")
            print()
        else:
            skipped_count += 1
            print(f"  ❌ Slide {slide.slide_number}: SKIPPED"
                  f" ({len(cleaned_content)} chars after cleaning)")

    print(f"\n{'=' * 60}")
    print(f"Results:")
    print(f"  Meaningful slides: {meaningful_count}")
    print(f"  Skipped slides:    {skipped_count}")
    print(f"  Total:             {len(slides)}")
    print(f"{'=' * 60}")