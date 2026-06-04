"""
azure_search_setup.py — Create Azure AI Search index
"""
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    SemanticConfiguration,
    SemanticSearch,
    SemanticPrioritizedFields,
    SemanticField,
)
from azure.core.credentials import AzureKeyCredential

# Configuration
SEARCH_ENDPOINT = "https://your-search-service.search.windows.net"
SEARCH_API_KEY = "your-search-admin-key"
INDEX_NAME = "arch-knowledge-index"

# Create client
client = SearchIndexClient(
    endpoint=SEARCH_ENDPOINT,
    credential=AzureKeyCredential(SEARCH_API_KEY),
)

# Define fields
fields = [
    SimpleField(name="id", type=SearchFieldDataType.String, key=True),
    SearchableField(name="content", type=SearchFieldDataType.String),
    SearchField(
        name="content_vector",
        type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
        searchable=True,
        vector_search_dimensions=1536,
        vector_search_profile_name="my-vector-profile",
    ),
    SimpleField(name="client", type=SearchFieldDataType.String,
                filterable=True, facetable=True),
    SimpleField(name="source_file", type=SearchFieldDataType.String,
                filterable=True),
    SimpleField(name="slide_number", type=SearchFieldDataType.String,
                filterable=True),
    SimpleField(name="section_type", type=SearchFieldDataType.String,
                filterable=True, facetable=True),
    SearchableField(name="title", type=SearchFieldDataType.String),
    SimpleField(name="chunk_index", type=SearchFieldDataType.Int32),
    SimpleField(name="ingested_at", type=SearchFieldDataType.DateTimeOffset,
                sortable=True),
]

# Vector search config
vector_search = VectorSearch(
    algorithms=[HnswAlgorithmConfiguration(name="hnsw-algo")],
    profiles=[VectorSearchProfile(name="my-vector-profile",
                                   algorithm_configuration_name="hnsw-algo")],
)

# Semantic ranker config
semantic_config = SemanticConfiguration(
    name="my-semantic-config",
    prioritized_fields=SemanticPrioritizedFields(
        content_fields=[SemanticField(field_name="content")],
        title_field=SemanticField(field_name="title"),
    ),
)

# Create index
index = SearchIndex(
    name=INDEX_NAME,
    fields=fields,
    vector_search=vector_search,
    semantic_search=SemanticSearch(configurations=[semantic_config]),
)

result = client.create_or_update_index(index)
print(f"✅ Index '{result.name}' created")