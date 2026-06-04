"""
Document Scanner — Discovers architecture documents in the folder structure
============================================================================

WHAT THIS MODULE DOES:
    Scans the data/documents/ directory and returns a list of all
    architecture files, organized by client.

    Your folder structure IS your metadata:
        data/documents/
        ├── DataStories/          ← client_name = "DataStories"
        │   └── blueprint.pptx    ← DocumentInfo for this file
        ├── TechNova/             ← client_name = "TechNova"
        │   └── hosting.pptx
        └── MediFlow/
            └── migration.pdf

WHY THIS IS SEPARATE FROM OTHER MODULES:
    Single Responsibility Principle (you know this from C#/SOLID).
    Scanner ONLY discovers files. It does NOT:
    - Read file contents (that's extractor.py)
    - Clean text (that's preprocessor.py)
    - Split into chunks (that's chunker.py)

PHASE 2 MIGRATION NOTE:
    In Azure-native version, this scanner would be replaced by:
    - Azure Blob Storage SDK → list containers and blobs
    - Container name = client name (same concept, different API)
    - Azure Functions trigger on blob upload (event-driven instead of scan)
"""

import logging
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import List

logger = logging.getLogger(__name__)


# ── Supported File Types ──────────────────────────────────────
# Only these extensions will be picked up by the scanner.
# Add more as you build extractors for them.
#
# PYTHON CONCEPT — set vs list:
#   We use a SET (curly braces) instead of a LIST (square brackets)
#   because we only need to check "is this extension supported?"
#   Sets do this in O(1) time. Lists do it in O(n) time.
#
#   C# equivalent: HashSet<string> vs List<string>
#       HashSet<string> supported = new() { ".pptx", ".pdf", ".docx" };
#       if (supported.Contains(ext)) { ... }

SUPPORTED_EXTENSIONS = {".pptx", ".pdf", ".docx"}


# ── DocumentInfo — Data Transfer Object ───────────────────────
#
# PYTHON CONCEPT — @dataclass:
#   A dataclass auto-generates __init__, __repr__, __eq__ for you.
#   Without it, you'd write:
#
#       class DocumentInfo:
#           def __init__(self, file_path, client_name, ...):
#               self.file_path = file_path
#               self.client_name = client_name
#               ...
#           def __repr__(self):
#               return f"DocumentInfo(file_path={self.file_path}, ...)"
#
#   With @dataclass, Python writes all that boilerplate for you.
#
#   C# equivalent: This is like a C# RECORD:
#       public record DocumentInfo(
#           string FilePath,
#           string ClientName,
#           string FileName,
#           string FileType,
#           int FileSize,
#           string LastModified
#       );
#
#   Both are immutable-by-convention data carriers.

@dataclass
class DocumentInfo:
    """
    Represents a discovered document with its metadata.

    Every field here becomes a constructor parameter AND an attribute:
        doc = DocumentInfo(file_path="/path", client_name="Client1", ...)
        print(doc.client_name)  # "Client1"
        print(doc)              # DocumentInfo(file_path='/path', client_name='Client1', ...)
    """
    file_path: str          # Full absolute path to the file
    client_name: str        # Auto-detected from parent folder name
    file_name: str          # Just the filename (e.g., "blueprint.pptx")
    file_type: str          # Extension (e.g., ".pptx")
    file_size: int          # Size in bytes
    last_modified: str      # ISO format timestamp (e.g., "2025-05-21T10:30:00")


class DocumentScanner:
    """
    Scans the documents directory to discover all client architecture files.

    KEY DESIGN DECISION:
        folder_name = client_name

    This means: no configuration file, no database, no manual tagging.
    Just create a folder called "DataStories" and drop files in it.
    The scanner automatically knows those files belong to DataStories.

    PYTHON CONCEPT — Type Hints (the ": str" and "-> List[...]" syntax):
        Python is dynamically typed — you CAN write:
            def scan(self):  # No hints — works, but unclear

        But type hints make code SELF-DOCUMENTING:
            def scan(self) -> List[DocumentInfo]:  # Clear: returns a list of DocumentInfo

        C# equivalent:
            public List<DocumentInfo> Scan() { ... }

        Python type hints are NOT enforced at runtime (unlike C#).
        They're for: readability, IDE autocomplete, and static analysis tools.
    """

    def __init__(self, documents_dir: str):
        """
        Initialize scanner with the documents directory path.

        PYTHON CONCEPT — Path (from pathlib):
            Path is modern Python's way to handle file paths.
            It replaces the old os.path module with an OBJECT-ORIENTED API.

            Old way (os.path — like C#'s Path.Combine):
                full_path = os.path.join(base, "subdir", "file.txt")
                exists = os.path.exists(full_path)
                ext = os.path.splitext(full_path)[1]

            New way (pathlib.Path — like C#'s DirectoryInfo/FileInfo):
                full_path = Path(base) / "subdir" / "file.txt"
                exists = full_path.exists()
                ext = full_path.suffix

            Path objects support:
                path / "child"     → join paths (like Path.Combine)
                path.exists()      → check existence
                path.is_dir()      → is it a directory?
                path.is_file()     → is it a file?
                path.iterdir()     → list contents (like Directory.EnumerateFiles)
                path.suffix        → get extension (".pptx")
                path.name          → get filename ("blueprint.pptx")
                path.stat()        → get file metadata (size, timestamps)
                path.mkdir()       → create directory

        Args:
            documents_dir: Path to the root documents directory
                          (e.g., "data/documents")
        """
        # PYTHON CONCEPT — Path() constructor:
        #   Path("data/documents") creates a Path object.
        #   Works on Windows (backslashes) and Linux (forward slashes) automatically.
        #   C# equivalent: new DirectoryInfo(@"data\documents")
        self.documents_dir = Path(documents_dir)

        # Create directory if it doesn't exist
        # parents=True → also creates parent directories (like mkdir -p)
        # exist_ok=True → don't error if already exists
        if not self.documents_dir.exists():
            logger.warning(f"Documents directory does not exist: {self.documents_dir}")
            self.documents_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created documents directory: {self.documents_dir}")

    def scan(self) -> List[DocumentInfo]:
        """
        Scan the documents directory and return all discovered documents.

        THE SCANNING ALGORITHM:
            1. List all subdirectories in data/documents/
            2. Each subdirectory = one client
            3. For each client directory, find supported files
            4. Return a DocumentInfo for each file

        PYTHON CONCEPT — .iterdir() vs os.listdir():
            Old way:
                for name in os.listdir("/some/path"):
                    full = os.path.join("/some/path", name)
                    if os.path.isdir(full): ...

            New way (what we use):
                for item in Path("/some/path").iterdir():
                    if item.is_dir(): ...

            .iterdir() returns Path objects directly, so you can
            immediately call .is_dir(), .name, .suffix, etc.

            C# equivalent: Directory.EnumerateDirectories() and
                          Directory.EnumerateFiles()

        Returns:
            List of DocumentInfo objects, one per discovered file.
        """
        documents = []

        # PYTHON CONCEPT — sorted():
        #   sorted() returns a NEW sorted list.
        #   .iterdir() returns items in arbitrary OS order.
        #   We sort for DETERMINISTIC behavior — same order every time.
        #   This matters for:
        #   - Reproducible testing
        #   - Consistent logging output
        #   - Predictable chunk ordering
        #
        #   C# equivalent: directory.EnumerateDirectories().OrderBy(d => d.Name)

        for client_dir in sorted(self.documents_dir.iterdir()):

            # Skip files at root level — only process directories
            if not client_dir.is_dir():
                logger.debug(f"Skipping non-directory: {client_dir.name}")
                continue

            # Skip hidden directories (starting with .)
            # WHY? On Mac/Linux, directories like .DS_Store, .git
            # start with a dot. We don't want to process these.
            if client_dir.name.startswith("."):
                logger.debug(f"Skipping hidden directory: {client_dir.name}")
                continue

            # ── The folder name IS the client name ──
            # This is our automatic metadata tagging strategy.
            # No config file needed. No database lookup.
            # Just: folder name → client name.
            client_name = client_dir.name
            logger.info(f"Scanning client: {client_name}")

            # Find all supported files in this client's folder
            file_count = 0
            for file_path in sorted(client_dir.iterdir()):
                if not file_path.is_file():
                    continue

                # PYTHON CONCEPT — .suffix:
                #   file_path.suffix returns the file extension including the dot.
                #   Example: Path("blueprint.pptx").suffix → ".pptx"
                #   .lower() normalizes case: ".PPTX" → ".pptx"
                #
                #   C# equivalent: Path.GetExtension(filePath).ToLower()
                ext = file_path.suffix.lower()

                # Check if this file type is supported
                # PYTHON CONCEPT — "in" operator with sets:
                #   ext in SUPPORTED_EXTENSIONS → O(1) lookup
                #   This is like HashSet.Contains() in C#
                if ext not in SUPPORTED_EXTENSIONS:
                    logger.debug(f"  Skipping unsupported: {file_path.name}")
                    continue

                # PYTHON CONCEPT — .stat():
                #   Returns file metadata (like FileInfo in C#):
                #   - stat.st_size    → file size in bytes
                #   - stat.st_mtime   → last modified time (Unix timestamp)
                #   - stat.st_ctime   → creation time
                #
                #   C# equivalent:
                #       var info = new FileInfo(path);
                #       info.Length     → size
                #       info.LastWriteTime → modified time
                stat = file_path.stat()

                doc_info = DocumentInfo(
                    file_path=str(file_path),
                    client_name=client_name,
                    file_name=file_path.name,
                    file_type=ext,
                    file_size=stat.st_size,
                    last_modified=datetime.fromtimestamp(
                        stat.st_mtime
                    ).isoformat(),
                )

                documents.append(doc_info)
                file_count += 1
                logger.info(
                    f"  Found: {file_path.name} "
                    f"({ext}, {stat.st_size:,} bytes)"
                )

            logger.info(f"  → {file_count} file(s) for {client_name}")

        logger.info(f"Total documents discovered: {len(documents)}")
        return documents

    def get_clients(self) -> List[str]:
        """
        Return a sorted list of all client names (subfolder names).

        Used by:
        - API /clients endpoint → populates UI dropdown
        - Retriever → validates client filter
        - Summary display

        PYTHON CONCEPT — List comprehension:
            This is a compact way to build a list:
                [item.name for item in path.iterdir() if item.is_dir()]

            Is equivalent to:
                result = []
                for item in path.iterdir():
                    if item.is_dir():
                        result.append(item.name)

            C# equivalent (LINQ):
                path.EnumerateDirectories()
                    .Select(d => d.Name)
                    .OrderBy(n => n)
                    .ToList();
        """
        clients = sorted([
            item.name
            for item in self.documents_dir.iterdir()
            if item.is_dir() and not item.name.startswith(".")
        ])
        return clients

    def get_summary(self) -> dict:
        """
        Return a summary of the documents directory.

        Useful for:
        - /stats API endpoint
        - Admin dashboard
        - Verifying ingestion setup

        Returns a dict like:
        {
            "total_files": 4,
            "total_clients": 3,
            "clients": ["DataStories", "MediFlow", "TechNova"],
            "files_by_type": {".pptx": 3, ".pdf": 1},
            "files_by_client": {"DataStories": 1, "MediFlow": 1, "TechNova": 2},
            "total_size_bytes": 162040,
        }
        """
        documents = self.scan()

        # Count files by type
        # PYTHON CONCEPT — dict.get(key, default):
        #   Returns the value if key exists, otherwise returns default.
        #   type_counts.get(".pptx", 0) → returns 0 if ".pptx" not yet in dict
        #   Then we add 1 to it.
        #
        #   C# equivalent:
        #       typeCounts.TryGetValue(".pptx", out var count);
        #       typeCounts[".pptx"] = count + 1;
        type_counts = {}
        for doc in documents:
            type_counts[doc.file_type] = type_counts.get(doc.file_type, 0) + 1

        # Count files by client
        client_counts = {}
        for doc in documents:
            client_counts[doc.client_name] = client_counts.get(doc.client_name, 0) + 1

        return {
            "total_files": len(documents),
            "total_clients": len(set(doc.client_name for doc in documents)),
            "clients": sorted(list(set(doc.client_name for doc in documents))),
            "files_by_type": type_counts,
            "files_by_client": client_counts,
            "total_size_bytes": sum(doc.file_size for doc in documents),
        }


# ── Standalone Testing ─────────────────────────────────────────
#
# PYTHON CONCEPT — if __name__ == "__main__":
#   This block ONLY runs when you execute this file directly:
#       python src/ingestion/scanner.py
#
#   It does NOT run when the file is imported:
#       from src.ingestion.scanner import DocumentScanner  ← block skipped
#
#   C# equivalent: There's no direct equivalent.
#   In C#, you'd create a separate console app for testing.
#   In Python, every file can be both a library AND a script.
#
#   This is extremely useful for testing individual modules.

if __name__ == "__main__":
    # Setup logging so we can see what's happening
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("=" * 50)
    print("Document Scanner — Standalone Test")
    print("=" * 50)

    # Scan from project root
    scanner = DocumentScanner("data/documents")

    # Show clients
    clients = scanner.get_clients()
    print(f"\nClients found: {clients}")

    # Scan all documents
    documents = scanner.scan()
    print(f"\nDocuments found: {len(documents)}")

    for doc in documents:
        size_kb = doc.file_size / 1024
        print(
            f"  📄 {doc.client_name}/{doc.file_name} "
            f"({doc.file_type}, {size_kb:.1f} KB)"
        )

    # Show summary
    summary = scanner.get_summary()
    print(f"\nSummary:")
    print(f"  Total files:   {summary['total_files']}")
    print(f"  Total clients: {summary['total_clients']}")
    print(f"  By type:       {summary['files_by_type']}")
    print(f"  By client:     {summary['files_by_client']}")
    print(f"  Total size:    {summary['total_size_bytes'] / 1024:.1f} KB")