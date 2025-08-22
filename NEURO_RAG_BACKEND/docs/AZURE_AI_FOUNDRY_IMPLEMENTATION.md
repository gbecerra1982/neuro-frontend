# Azure AI Foundry Implementation Guide for NEURO RAG

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Step-by-Step Configuration](#step-by-step-configuration)
3. [Document Layout Skill Setup](#document-layout-skill-setup)
4. [Index Creation with Chunks](#index-creation-with-chunks)
5. [Migration Scripts](#migration-scripts)
6. [Validation and Testing](#validation-and-testing)
7. [Production Deployment](#production-deployment)

## Prerequisites

### Required Azure Services
- Azure AI Foundry (formerly Azure AI Studio)
- Azure Cognitive Search (Standard tier or higher)
- Azure Document Intelligence
- Azure OpenAI Service
- Azure Blob Storage

### Service Regions
Ensure all services are in supported regions:
- East US
- West Europe
- North Central US

### Access Requirements
- Azure subscription with Owner or Contributor role
- Azure AI Foundry workspace created
- Service endpoints and API keys ready

## Step-by-Step Configuration

### 1. Access Azure AI Foundry

Navigate to [https://ai.azure.com](https://ai.azure.com) and sign in.

### 2. Create or Select Project

```
Home → Projects → + New project
```

Configuration:
- **Project name**: `neuro-rag-production`
- **Resource group**: Select existing or create new
- **Location**: East US (recommended)

### 3. Connect Azure Services

#### 3.1 Connect Azure Cognitive Search

```
Project → Settings → Connected resources → + Add connection
→ Azure AI Search → Select your service
```

Verify connection:
- Service name: `your-search-service`
- Endpoint: `https://your-search-service.search.windows.net`
- Authentication: Key-based

#### 3.2 Connect Azure OpenAI

```
Project → Settings → Connected resources → + Add connection
→ Azure OpenAI → Select your service
```

#### 3.3 Connect Azure Storage

```
Project → Settings → Connected resources → + Add connection
→ Azure Storage → Select your storage account
```

## Document Layout Skill Setup

### 1. Navigate to Knowledge Base

```
Project → Agents → Setup → Knowledge → + Add
```

### 2. Configure Import Wizard

#### Step 1: Select Data Source
- Choose **Azure Blob Storage**
- Container: `neuro-documents`
- Folder path: `/pozos/`

#### Step 2: Enable Document Processing
```json
{
  "extractionMode": "documentLayout",
  "chunkingMode": "semantic",
  "enableHierarchicalExtraction": true
}
```

#### Step 3: Configure Skillset
Select **Create new skillset** with these settings:

```json
{
  "@odata.type": "#Microsoft.Azure.Search.Skillsets",
  "name": "neuro-document-layout-skillset",
  "description": "Semantic chunking for oil well documents",
  "skills": [
    {
      "@odata.type": "#Microsoft.Skills.Util.DocumentIntelligenceLayoutSkill",
      "name": "document-layout",
      "description": "Extract document structure with semantic chunking",
      "context": "/document",
      "outputMode": "oneToMany",
      "markdownHeaderDepth": "h3",
      "analyzeLayout": true,
      "inputs": [
        {
          "name": "file_data",
          "source": "/document/file_data"
        }
      ],
      "outputs": [
        {
          "name": "chunks",
          "targetName": "layoutChunks"
        }
      ]
    },
    {
      "@odata.type": "#Microsoft.Skills.Text.SplitSkill",
      "name": "text-chunker",
      "description": "Split text into semantic chunks",
      "context": "/document/layoutChunks/*",
      "textSplitMode": "pages",
      "maximumPageLength": 1000,
      "pageOverlapLength": 200,
      "inputs": [
        {
          "name": "text",
          "source": "/document/layoutChunks/*/content"
        }
      ],
      "outputs": [
        {
          "name": "textItems",
          "targetName": "chunks"
        }
      ]
    },
    {
      "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
      "name": "embedding-generator",
      "description": "Generate embeddings for chunks",
      "context": "/document/layoutChunks/*/chunks/*",
      "resourceUri": "YOUR_OPENAI_ENDPOINT",
      "apiKey": "YOUR_OPENAI_KEY",
      "deploymentId": "text-embedding-ada-002",
      "inputs": [
        {
          "name": "text",
          "source": "/document/layoutChunks/*/chunks/*"
        }
      ],
      "outputs": [
        {
          "name": "embedding",
          "targetName": "text_vector"
        }
      ]
    }
  ]
}
```

### 3. Configure Index Mapping

#### Field Mappings
| Source Path | Target Field | Description |
|------------|--------------|-------------|
| /document/layoutChunks/*/chunks/* | chunk_content | Chunk text content |
| /document/layoutChunks/*/chunkId | chunk_id | Unique chunk identifier |
| /document/layoutChunks/*/parentId | parent_id | Parent document ID |
| /document/layoutChunks/*/chunkIndex | chunk_index | Chunk sequence number |
| /document/layoutChunks/*/headers/h1 | header_1 | Main section |
| /document/layoutChunks/*/headers/h2 | header_2 | Subsection |
| /document/layoutChunks/*/headers/h3 | header_3 | Sub-subsection |
| /document/metadata/well_name | pozo | Well name |
| /document/metadata/equipment | equipo | Equipment code |
| /document/metadata/date | fecha | Document date |
| /document/metadata/field | yacimiento | Oil field |

### 4. Configure Semantic Search

#### Semantic Configuration
```json
{
  "name": "neuro-semantic-config",
  "prioritizedFields": {
    "titleField": {
      "fieldName": "header_1"
    },
    "prioritizedContentFields": [
      {
        "fieldName": "chunk_content"
      }
    ],
    "prioritizedKeywordsFields": [
      {
        "fieldName": "pozo"
      },
      {
        "fieldName": "equipo"
      },
      {
        "fieldName": "yacimiento"
      }
    ]
  }
}
```

### 5. Configure Vector Search

```json
{
  "vectorSearch": {
    "algorithms": [
      {
        "name": "hnsw-algorithm",
        "kind": "hnsw",
        "hnswParameters": {
          "metric": "cosine",
          "m": 4,
          "efConstruction": 400,
          "efSearch": 500
        }
      }
    ],
    "profiles": [
      {
        "name": "vector-profile-1536",
        "algorithm": "hnsw-algorithm",
        "vectorizer": "openai-ada-002"
      }
    ]
  }
}
```

## Index Creation with Chunks

### 1. Create Index via Portal

In Azure AI Foundry:
```
Knowledge → Indexes → + Create index
```

Settings:
- **Index name**: `neuro-rag-semantic-chunks`
- **Search type**: Hybrid (Vector + Keyword + Semantic)
- **Document Layout**: Enabled
- **Chunk size**: 1000 tokens
- **Chunk overlap**: 200 tokens

### 2. Import Documents

#### Prepare Document Structure
```
/pozos/
├── LACh-1030/
│   ├── metadata.json
│   ├── 2024-01-15_daily_report.pdf
│   └── 2024-01-16_daily_report.pdf
├── AdCh-1117/
│   ├── metadata.json
│   └── 2024-01-15_daily_report.pdf
```

#### Metadata Format
```json
{
  "well_name": "LACh-1030(h)",
  "equipment": "DLS-168",
  "date": "2024-01-15",
  "field": "Vaca Muerta",
  "document_type": "daily_report",
  "operator": "YPF",
  "region": "Neuquen"
}
```

### 3. Start Indexing

```
Indexers → neuro-document-indexer → Run
```

Monitor progress:
- Documents processed
- Chunks created
- Errors/warnings

## Migration Scripts

### 1. Prepare Migration Script

Create `scripts/migrate_to_chunks.py`:

```python
import os
import json
import logging
from typing import Dict, List, Any
from datetime import datetime
from azure.search.documents import SearchClient
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
    SemanticPrioritizedFields,
    SemanticField,
    SemanticSearch
)
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChunkMigrator:
    """
    Migrate existing index to semantic chunks
    """
    
    def __init__(self):
        self.endpoint = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
        self.api_key = os.environ["AZURE_SEARCH_ADMIN_KEY"]
        self.old_index = os.environ.get("AZURE_SEARCH_INDEX_OLD", "neuro-rag")
        self.new_index = os.environ.get("AZURE_SEARCH_INDEX", "neuro-rag-semantic-chunks")
        
        self.index_client = SearchIndexClient(
            endpoint=self.endpoint,
            credential=AzureKeyCredential(self.api_key)
        )
        
    def create_chunk_index(self) -> bool:
        """
        Create new index with chunk structure
        """
        try:
            # Define fields
            fields = [
                SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True),
                SimpleField(name="parent_id", type=SearchFieldDataType.String, filterable=True),
                SearchableField(name="chunk_content", type=SearchFieldDataType.String),
                SimpleField(name="chunk_index", type=SearchFieldDataType.Int32, sortable=True),
                SearchableField(name="header_1", type=SearchFieldDataType.String, facetable=True),
                SearchableField(name="header_2", type=SearchFieldDataType.String, facetable=True),
                SearchableField(name="header_3", type=SearchFieldDataType.String, facetable=True),
                SearchableField(name="pozo", type=SearchFieldDataType.String, facetable=True, filterable=True),
                SearchableField(name="equipo", type=SearchFieldDataType.String, facetable=True, filterable=True),
                SimpleField(name="fecha", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
                SearchableField(name="yacimiento", type=SearchFieldDataType.String, facetable=True, filterable=True),
                SimpleField(name="tipo_documento", type=SearchFieldDataType.String, facetable=True, filterable=True),
                SearchField(
                    name="text_vector",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=1536,
                    vector_search_profile_name="vector-profile-1536"
                ),
                SimpleField(name="metadata_json", type=SearchFieldDataType.String)
            ]
            
            # Vector search configuration
            vector_search = VectorSearch(
                algorithms=[
                    HnswAlgorithmConfiguration(
                        name="hnsw-algorithm",
                        parameters={
                            "m": 4,
                            "efConstruction": 400,
                            "efSearch": 500,
                            "metric": "cosine"
                        }
                    )
                ],
                profiles=[
                    VectorSearchProfile(
                        name="vector-profile-1536",
                        algorithm_configuration_name="hnsw-algorithm"
                    )
                ]
            )
            
            # Semantic search configuration
            semantic_search = SemanticSearch(
                default_configuration_name="neuro-semantic-config",
                configurations=[
                    SemanticConfiguration(
                        name="neuro-semantic-config",
                        prioritized_fields=SemanticPrioritizedFields(
                            title_field=SemanticField(field_name="header_1"),
                            content_fields=[SemanticField(field_name="chunk_content")],
                            keywords_fields=[
                                SemanticField(field_name="pozo"),
                                SemanticField(field_name="equipo"),
                                SemanticField(field_name="header_2")
                            ]
                        )
                    )
                ]
            )
            
            # Create index
            index = SearchIndex(
                name=self.new_index,
                fields=fields,
                vector_search=vector_search,
                semantic_search=semantic_search
            )
            
            self.index_client.create_or_update_index(index)
            logger.info(f"Created index: {self.new_index}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            return False
    
    def validate_migration(self) -> Dict[str, Any]:
        """
        Validate the migration was successful
        """
        try:
            # Get index statistics
            old_client = SearchClient(
                endpoint=self.endpoint,
                index_name=self.old_index,
                credential=AzureKeyCredential(self.api_key)
            )
            
            new_client = SearchClient(
                endpoint=self.endpoint,
                index_name=self.new_index,
                credential=AzureKeyCredential(self.api_key)
            )
            
            # Count documents
            old_count = old_client.get_document_count()
            new_count = new_client.get_document_count()
            
            # Test search
            test_query = "equipo DLS-168"
            old_results = list(old_client.search(test_query, top=1))
            new_results = list(new_client.search(test_query, top=1))
            
            validation = {
                "timestamp": datetime.now().isoformat(),
                "old_index": {
                    "name": self.old_index,
                    "document_count": old_count,
                    "test_search_results": len(old_results)
                },
                "new_index": {
                    "name": self.new_index,
                    "chunk_count": new_count,
                    "test_search_results": len(new_results)
                },
                "status": "success" if new_count > 0 else "pending"
            }
            
            return validation
            
        except Exception as e:
            return {
                "error": str(e),
                "status": "failed"
            }

if __name__ == "__main__":
    migrator = ChunkMigrator()
    
    # Create new index
    if migrator.create_chunk_index():
        print("Index created successfully")
        
        # Note: Actual document chunking happens in Azure AI Foundry
        print("\nNext steps:")
        print("1. Go to Azure AI Foundry portal")
        print("2. Import documents using Document Layout Skill")
        print("3. Run validation after import completes")
        
        # Validate migration
        validation = migrator.validate_migration()
        print(f"\nValidation: {json.dumps(validation, indent=2)}")
```

### 2. Create Validation Script

Create `scripts/validate_chunks.py`:

```python
import os
import logging
from typing import Dict, List, Any
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChunkValidator:
    """
    Validate semantic chunks quality
    """
    
    def __init__(self):
        self.endpoint = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
        self.api_key = os.environ["AZURE_SEARCH_ADMIN_KEY"]
        self.index_name = os.environ["AZURE_SEARCH_INDEX"]
        
        self.client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=AzureKeyCredential(self.api_key)
        )
    
    def validate_chunk_structure(self) -> Dict[str, Any]:
        """
        Validate chunk structure and relationships
        """
        results = {
            "total_chunks": 0,
            "unique_parents": set(),
            "chunks_per_parent": {},
            "average_chunk_size": 0,
            "orphan_chunks": 0,
            "issues": []
        }
        
        try:
            # Get sample of chunks
            search_results = self.client.search(
                search_text="*",
                top=1000,
                select=["chunk_id", "parent_id", "chunk_content", "chunk_index"]
            )
            
            total_content_length = 0
            
            for doc in search_results:
                results["total_chunks"] += 1
                
                parent_id = doc.get("parent_id")
                if parent_id:
                    results["unique_parents"].add(parent_id)
                    if parent_id not in results["chunks_per_parent"]:
                        results["chunks_per_parent"][parent_id] = 0
                    results["chunks_per_parent"][parent_id] += 1
                else:
                    results["orphan_chunks"] += 1
                    results["issues"].append(f"Orphan chunk: {doc.get('chunk_id')}")
                
                content = doc.get("chunk_content", "")
                total_content_length += len(content)
            
            # Calculate statistics
            if results["total_chunks"] > 0:
                results["average_chunk_size"] = total_content_length / results["total_chunks"]
            
            results["unique_parents"] = len(results["unique_parents"])
            
            # Check for issues
            for parent_id, count in results["chunks_per_parent"].items():
                if count < 2:
                    results["issues"].append(f"Parent {parent_id} has only {count} chunk")
            
            return results
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return {"error": str(e)}
    
    def test_semantic_search(self) -> Dict[str, Any]:
        """
        Test semantic search capabilities
        """
        test_queries = [
            "ubicacion del equipo DLS-168",
            "problemas operacionales pozo LACh-1030",
            "produccion diaria yacimiento Vaca Muerta",
            "reporte de perforacion fecha 2024-01-15"
        ]
        
        results = {
            "test_results": []
        }
        
        for query in test_queries:
            try:
                search_results = list(self.client.search(
                    search_text=query,
                    query_type="semantic",
                    semantic_configuration_name="neuro-semantic-config",
                    top=5
                ))
                
                results["test_results"].append({
                    "query": query,
                    "results_count": len(search_results),
                    "top_score": search_results[0]["@search.score"] if search_results else 0,
                    "has_semantic_answer": any("@search.captions" in r for r in search_results)
                })
                
            except Exception as e:
                results["test_results"].append({
                    "query": query,
                    "error": str(e)
                })
        
        return results
    
    def generate_report(self) -> str:
        """
        Generate comprehensive validation report
        """
        report = []
        report.append("=" * 60)
        report.append("CHUNK VALIDATION REPORT")
        report.append("=" * 60)
        
        # Structure validation
        structure = self.validate_chunk_structure()
        report.append("\n1. CHUNK STRUCTURE")
        report.append("-" * 30)
        report.append(f"Total chunks: {structure.get('total_chunks', 0)}")
        report.append(f"Unique documents: {structure.get('unique_parents', 0)}")
        report.append(f"Average chunk size: {structure.get('average_chunk_size', 0):.0f} chars")
        report.append(f"Orphan chunks: {structure.get('orphan_chunks', 0)}")
        
        if structure.get("issues"):
            report.append(f"\nIssues found: {len(structure['issues'])}")
            for issue in structure["issues"][:5]:
                report.append(f"  - {issue}")
        
        # Search validation
        search = self.test_semantic_search()
        report.append("\n2. SEMANTIC SEARCH")
        report.append("-" * 30)
        
        for test in search.get("test_results", []):
            report.append(f"\nQuery: {test['query']}")
            if "error" in test:
                report.append(f"  Error: {test['error']}")
            else:
                report.append(f"  Results: {test['results_count']}")
                report.append(f"  Top score: {test['top_score']:.3f}")
                report.append(f"  Semantic answer: {test['has_semantic_answer']}")
        
        report.append("\n" + "=" * 60)
        return "\n".join(report)

if __name__ == "__main__":
    validator = ChunkValidator()
    report = validator.generate_report()
    print(report)
    
    # Save report
    with open("chunk_validation_report.txt", "w") as f:
        f.write(report)
    print("\nReport saved to chunk_validation_report.txt")
```

## Validation and Testing

### 1. Pre-Migration Checklist

- [ ] All services connected in Azure AI Foundry
- [ ] Document Intelligence API key configured
- [ ] Storage container has correct structure
- [ ] Metadata files prepared for each document
- [ ] Environment variables updated

### 2. Post-Migration Tests

Run validation script:
```bash
python scripts/validate_chunks.py
```

Expected results:
- Average chunk size: 800-1200 characters
- Chunks per document: 10-50
- Orphan chunks: 0
- Semantic search success rate: >90%

### 3. Performance Benchmarks

Compare before/after:
- Query latency: <2s (from 7-10s)
- Search accuracy: >90% (from 60%)
- Cache hit rate: >30%
- Memory usage: <500MB

## Production Deployment

### 1. Update Application Configuration

In `.env`:
```env
# Switch to chunked index
AZURE_SEARCH_INDEX=neuro-rag-semantic-chunks
USE_UNIFIED_AGENT=true
RAG_SEARCH_MODE=hybrid
RAG_INCLUDE_PARENT_CONTEXT=true
```

### 2. Deploy with Zero Downtime

```bash
# Deploy new version
git checkout -b deploy-chunks
git add .
git commit -m "Deploy semantic chunking"

# Test in staging
export ENVIRONMENT=staging
python src/api/main.py

# Switch production
export ENVIRONMENT=production
systemctl restart neuro-rag-backend
```

### 3. Monitor Production

Key metrics:
- Response time P95: <3s
- Error rate: <1%
- Search success rate: >95%
- User satisfaction: Track improvement

### 4. Rollback Plan

If issues occur:
```bash
# Quick rollback
export AZURE_SEARCH_INDEX=neuro-rag
export USE_UNIFIED_AGENT=false
systemctl restart neuro-rag-backend
```

## Troubleshooting

### Common Issues

#### 1. Document Layout Skill Not Available
**Solution**: Ensure region supports Document Intelligence v3.0+

#### 2. Chunks Too Small/Large
**Solution**: Adjust `maximumPageLength` in skillset (600-1200 recommended)

#### 3. Missing Headers in Chunks
**Solution**: Verify `markdownHeaderDepth` is set to h3 or deeper

#### 4. Slow Indexing
**Solution**: Batch documents, use parallel processing

#### 5. Vector Search Not Working
**Solution**: Verify embedding model deployment and API key

### Debug Commands

Check index status:
```python
from azure.search.documents import SearchClient
client = SearchClient(endpoint, index_name, credential)
print(f"Document count: {client.get_document_count()}")
```

Test chunking:
```python
results = client.search("*", select=["chunk_id", "parent_id"], top=10)
for r in results:
    print(f"Chunk: {r['chunk_id']} -> Parent: {r['parent_id']}")
```

## Next Steps

After successful implementation:

1. **Fine-tune chunk parameters** based on your document characteristics
2. **Implement incremental updates** for new documents
3. **Set up monitoring dashboards** in Application Insights
4. **Train team** on new search capabilities
5. **Document query patterns** for optimization

## Support Resources

- [Azure AI Foundry Documentation](https://learn.microsoft.com/azure/ai-studio/)
- [Document Intelligence Layout](https://learn.microsoft.com/azure/ai-services/document-intelligence/concept-layout)
- [Cognitive Search Semantic](https://learn.microsoft.com/azure/search/semantic-search-overview)
- [Vector Search Guide](https://learn.microsoft.com/azure/search/vector-search-overview)