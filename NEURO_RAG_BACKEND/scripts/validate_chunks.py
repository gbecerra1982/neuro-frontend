"""
Validation script for semantic chunks in NEURO RAG
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict
from azure.search.documents import SearchClient
from azure.search.documents.models import QueryType
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ChunkValidator:
    """
    Comprehensive validation for semantic chunks quality
    """
    
    def __init__(self):
        # Azure Search configuration
        self.endpoint = os.environ["AZURE_SEARCH_SERVICE_ENDPOINT"]
        self.api_key = os.environ["AZURE_SEARCH_ADMIN_KEY"]
        self.index_name = os.environ.get("AZURE_SEARCH_INDEX", "neuro-rag-semantic-chunks")
        
        # Initialize client
        self.client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=AzureKeyCredential(self.api_key)
        )
        
        logger.info(f"Initialized validator for index: {self.index_name}")
    
    def validate_chunk_structure(self) -> Dict[str, Any]:
        """
        Validate chunk structure and relationships
        """
        logger.info("Validating chunk structure...")
        
        results = {
            "total_chunks": 0,
            "unique_parents": set(),
            "chunks_per_parent": defaultdict(int),
            "chunk_sizes": [],
            "orphan_chunks": [],
            "missing_fields": defaultdict(list),
            "header_coverage": {
                "header_1": 0,
                "header_2": 0,
                "header_3": 0
            },
            "metadata_coverage": {
                "pozo": 0,
                "equipo": 0,
                "fecha": 0,
                "yacimiento": 0
            },
            "issues": []
        }
        
        try:
            # Get all chunks (limited sample for performance)
            search_results = self.client.search(
                search_text="*",
                top=1000,
                select=[
                    "chunk_id", "parent_id", "chunk_content", "chunk_index",
                    "header_1", "header_2", "header_3",
                    "pozo", "equipo", "fecha", "yacimiento"
                ]
            )
            
            for doc in search_results:
                results["total_chunks"] += 1
                
                # Check parent relationship
                parent_id = doc.get("parent_id")
                if parent_id:
                    results["unique_parents"].add(parent_id)
                    results["chunks_per_parent"][parent_id] += 1
                else:
                    results["orphan_chunks"].append(doc.get("chunk_id"))
                
                # Analyze chunk content
                content = doc.get("chunk_content", "")
                if content:
                    results["chunk_sizes"].append(len(content))
                else:
                    results["missing_fields"]["chunk_content"].append(doc.get("chunk_id"))
                
                # Check headers
                for header in ["header_1", "header_2", "header_3"]:
                    if doc.get(header):
                        results["header_coverage"][header] += 1
                
                # Check metadata
                for field in ["pozo", "equipo", "fecha", "yacimiento"]:
                    if doc.get(field):
                        results["metadata_coverage"][field] += 1
                
                # Validate chunk index
                chunk_index = doc.get("chunk_index")
                if chunk_index is None:
                    results["missing_fields"]["chunk_index"].append(doc.get("chunk_id"))
            
            # Calculate statistics
            results["unique_parents"] = len(results["unique_parents"])
            
            if results["chunk_sizes"]:
                results["avg_chunk_size"] = sum(results["chunk_sizes"]) / len(results["chunk_sizes"])
                results["min_chunk_size"] = min(results["chunk_sizes"])
                results["max_chunk_size"] = max(results["chunk_sizes"])
            
            # Identify issues
            if results["orphan_chunks"]:
                results["issues"].append(f"Found {len(results['orphan_chunks'])} orphan chunks")
            
            for parent_id, count in results["chunks_per_parent"].items():
                if count == 1:
                    results["issues"].append(f"Parent {parent_id} has only 1 chunk")
            
            if results["avg_chunk_size"] < 500:
                results["issues"].append(f"Average chunk size too small: {results['avg_chunk_size']:.0f} chars")
            elif results["avg_chunk_size"] > 5000:
                results["issues"].append(f"Average chunk size too large: {results['avg_chunk_size']:.0f} chars")
            
            # Calculate coverage percentages
            if results["total_chunks"] > 0:
                for header in results["header_coverage"]:
                    results["header_coverage"][header] = (
                        results["header_coverage"][header] / results["total_chunks"] * 100
                    )
                for field in results["metadata_coverage"]:
                    results["metadata_coverage"][field] = (
                        results["metadata_coverage"][field] / results["total_chunks"] * 100
                    )
            
            return results
            
        except Exception as e:
            logger.error(f"Structure validation error: {e}", exc_info=True)
            return {"error": str(e)}
    
    def test_semantic_search(self) -> Dict[str, Any]:
        """
        Test semantic search capabilities with domain-specific queries
        """
        logger.info("Testing semantic search...")
        
        test_queries = [
            {
                "query": "ubicacion del equipo DLS-168",
                "expected_fields": ["equipo", "pozo"],
                "type": "equipment_location"
            },
            {
                "query": "problemas operacionales pozo LACh-1030",
                "expected_fields": ["pozo"],
                "type": "operational_issues"
            },
            {
                "query": "produccion diaria yacimiento Vaca Muerta",
                "expected_fields": ["yacimiento"],
                "type": "production_data"
            },
            {
                "query": "reporte de perforacion fecha 2024-01-15",
                "expected_fields": ["fecha", "tipo_documento"],
                "type": "drilling_report"
            },
            {
                "query": "novedades del equipo en el ultimo turno",
                "expected_fields": ["equipo"],
                "type": "shift_updates"
            }
        ]
        
        results = {
            "test_results": [],
            "success_rate": 0,
            "avg_response_time": 0,
            "semantic_answer_rate": 0
        }
        
        response_times = []
        successful_tests = 0
        semantic_answers = 0
        
        for test in test_queries:
            try:
                start_time = datetime.now()
                
                # Execute semantic search
                search_results = list(self.client.search(
                    search_text=test["query"],
                    query_type=QueryType.SEMANTIC,
                    semantic_configuration_name="neuro-semantic-config",
                    top=5,
                    include_total_count=True
                ))
                
                response_time = (datetime.now() - start_time).total_seconds()
                response_times.append(response_time)
                
                # Analyze results
                test_result = {
                    "query": test["query"],
                    "type": test["type"],
                    "results_count": len(search_results),
                    "response_time": response_time,
                    "has_results": len(search_results) > 0
                }
                
                if search_results:
                    # Check top result
                    top_result = search_results[0]
                    test_result["top_score"] = top_result.get("@search.score", 0)
                    test_result["has_reranker_score"] = "@search.reranker_score" in top_result
                    
                    # Check for semantic captions
                    if "@search.captions" in top_result:
                        captions = top_result["@search.captions"]
                        test_result["has_semantic_caption"] = len(captions) > 0
                        semantic_answers += 1
                    else:
                        test_result["has_semantic_caption"] = False
                    
                    # Validate expected fields
                    fields_found = []
                    for field in test["expected_fields"]:
                        if top_result.get(field):
                            fields_found.append(field)
                    
                    test_result["expected_fields_found"] = fields_found
                    test_result["validation_passed"] = len(fields_found) > 0
                    
                    if test_result["validation_passed"]:
                        successful_tests += 1
                
                results["test_results"].append(test_result)
                
            except Exception as e:
                results["test_results"].append({
                    "query": test["query"],
                    "error": str(e)
                })
                logger.error(f"Search test error for '{test['query']}': {e}")
        
        # Calculate metrics
        total_tests = len(test_queries)
        if total_tests > 0:
            results["success_rate"] = (successful_tests / total_tests) * 100
            results["semantic_answer_rate"] = (semantic_answers / total_tests) * 100
        
        if response_times:
            results["avg_response_time"] = sum(response_times) / len(response_times)
            results["min_response_time"] = min(response_times)
            results["max_response_time"] = max(response_times)
        
        return results
    
    def test_vector_search(self) -> Dict[str, Any]:
        """
        Test vector search capabilities
        """
        logger.info("Testing vector search...")
        
        test_queries = [
            "equipment maintenance procedures",
            "drilling depth measurements",
            "production optimization strategies"
        ]
        
        results = {
            "vector_search_enabled": False,
            "test_results": []
        }
        
        try:
            # Test if vector search is working
            for query in test_queries:
                search_results = list(self.client.search(
                    search_text=query,
                    top=3,
                    vector_queries=[{
                        "kind": "text",
                        "text": query,
                        "k_nearest_neighbors": 3,
                        "fields": "text_vector"
                    }]
                ))
                
                results["test_results"].append({
                    "query": query,
                    "results_count": len(search_results),
                    "has_vector_scores": any("@search.score" in r for r in search_results)
                })
                
                if len(search_results) > 0:
                    results["vector_search_enabled"] = True
            
        except Exception as e:
            logger.warning(f"Vector search test failed: {e}")
            results["error"] = str(e)
        
        return results
    
    def test_filtering(self) -> Dict[str, Any]:
        """
        Test filtering capabilities
        """
        logger.info("Testing filtering...")
        
        filter_tests = [
            {
                "filter": "pozo eq 'LACh-1030(h)'",
                "description": "Filter by well"
            },
            {
                "filter": "equipo eq 'DLS-168'",
                "description": "Filter by equipment"
            },
            {
                "filter": "yacimiento eq 'Vaca Muerta'",
                "description": "Filter by field"
            },
            {
                "filter": "fecha ge 2024-01-01T00:00:00Z",
                "description": "Filter by date range"
            }
        ]
        
        results = {
            "filter_tests": []
        }
        
        for test in filter_tests:
            try:
                search_results = list(self.client.search(
                    search_text="*",
                    filter=test["filter"],
                    top=5
                ))
                
                results["filter_tests"].append({
                    "filter": test["filter"],
                    "description": test["description"],
                    "results_count": len(search_results),
                    "status": "success" if len(search_results) > 0 else "no_results"
                })
                
            except Exception as e:
                results["filter_tests"].append({
                    "filter": test["filter"],
                    "description": test["description"],
                    "error": str(e),
                    "status": "failed"
                })
        
        return results
    
    def check_data_quality(self) -> Dict[str, Any]:
        """
        Check overall data quality
        """
        logger.info("Checking data quality...")
        
        results = {
            "total_documents": self.client.get_document_count(),
            "quality_checks": []
        }
        
        # Sample documents for quality check
        sample = list(self.client.search(
            search_text="*",
            top=100,
            select=["chunk_id", "chunk_content", "pozo", "equipo", "fecha"]
        ))
        
        # Check for common issues
        empty_content = sum(1 for doc in sample if not doc.get("chunk_content", "").strip())
        missing_metadata = sum(1 for doc in sample if not doc.get("pozo") and not doc.get("equipo"))
        
        results["quality_checks"] = [
            {
                "check": "Empty content",
                "count": empty_content,
                "percentage": (empty_content / len(sample) * 100) if sample else 0,
                "status": "pass" if empty_content == 0 else "warning"
            },
            {
                "check": "Missing metadata",
                "count": missing_metadata,
                "percentage": (missing_metadata / len(sample) * 100) if sample else 0,
                "status": "pass" if missing_metadata < 5 else "warning"
            }
        ]
        
        return results
    
    def generate_report(self) -> str:
        """
        Generate comprehensive validation report
        """
        report = []
        report.append("=" * 80)
        report.append("SEMANTIC CHUNK VALIDATION REPORT")
        report.append("=" * 80)
        report.append(f"Index: {self.index_name}")
        report.append(f"Timestamp: {datetime.now().isoformat()}")
        report.append("")
        
        # 1. Structure validation
        structure = self.validate_chunk_structure()
        report.append("1. CHUNK STRUCTURE")
        report.append("-" * 40)
        
        if "error" not in structure:
            report.append(f"Total chunks: {structure.get('total_chunks', 0):,}")
            report.append(f"Unique documents: {structure.get('unique_parents', 0):,}")
            
            if "avg_chunk_size" in structure:
                report.append(f"Average chunk size: {structure['avg_chunk_size']:.0f} chars")
                report.append(f"Size range: {structure['min_chunk_size']}-{structure['max_chunk_size']} chars")
            
            report.append(f"Orphan chunks: {len(structure.get('orphan_chunks', []))}")
            
            report.append("\nHeader Coverage:")
            for header, coverage in structure.get("header_coverage", {}).items():
                report.append(f"  {header}: {coverage:.1f}%")
            
            report.append("\nMetadata Coverage:")
            for field, coverage in structure.get("metadata_coverage", {}).items():
                report.append(f"  {field}: {coverage:.1f}%")
            
            if structure.get("issues"):
                report.append(f"\nIssues ({len(structure['issues'])}):")
                for issue in structure["issues"][:10]:
                    report.append(f"  - {issue}")
        else:
            report.append(f"ERROR: {structure['error']}")
        
        report.append("")
        
        # 2. Semantic search validation
        semantic = self.test_semantic_search()
        report.append("2. SEMANTIC SEARCH")
        report.append("-" * 40)
        
        if "error" not in semantic:
            report.append(f"Success rate: {semantic['success_rate']:.1f}%")
            report.append(f"Semantic answer rate: {semantic['semantic_answer_rate']:.1f}%")
            
            if "avg_response_time" in semantic:
                report.append(f"Avg response time: {semantic['avg_response_time']:.2f}s")
                report.append(f"Response time range: {semantic['min_response_time']:.2f}-{semantic['max_response_time']:.2f}s")
            
            report.append("\nQuery Results:")
            for test in semantic.get("test_results", [])[:5]:
                if "error" not in test:
                    report.append(f"  Query: {test['query'][:50]}...")
                    report.append(f"    Results: {test['results_count']}")
                    report.append(f"    Response time: {test.get('response_time', 0):.2f}s")
                    report.append(f"    Validation: {'PASS' if test.get('validation_passed') else 'FAIL'}")
        else:
            report.append(f"ERROR: {semantic['error']}")
        
        report.append("")
        
        # 3. Vector search validation
        vector = self.test_vector_search()
        report.append("3. VECTOR SEARCH")
        report.append("-" * 40)
        
        if "error" not in vector:
            report.append(f"Vector search enabled: {'YES' if vector['vector_search_enabled'] else 'NO'}")
            
            for test in vector.get("test_results", []):
                report.append(f"  Query: {test['query']}")
                report.append(f"    Results: {test['results_count']}")
        else:
            report.append(f"WARNING: {vector['error']}")
        
        report.append("")
        
        # 4. Filtering validation
        filtering = self.test_filtering()
        report.append("4. FILTERING")
        report.append("-" * 40)
        
        for test in filtering.get("filter_tests", []):
            status_icon = "OK" if test["status"] == "success" else "FAIL"
            report.append(f"  [{status_icon}] {test['description']}")
            if "error" in test:
                report.append(f"       Error: {test['error']}")
            else:
                report.append(f"       Results: {test['results_count']}")
        
        report.append("")
        
        # 5. Data quality
        quality = self.check_data_quality()
        report.append("5. DATA QUALITY")
        report.append("-" * 40)
        report.append(f"Total documents in index: {quality['total_documents']:,}")
        
        for check in quality.get("quality_checks", []):
            status_icon = "OK" if check["status"] == "pass" else "WARN"
            report.append(f"  [{status_icon}] {check['check']}: {check['percentage']:.1f}% ({check['count']} items)")
        
        report.append("")
        
        # Summary
        report.append("SUMMARY")
        report.append("-" * 40)
        
        # Determine overall status
        critical_issues = []
        warnings = []
        
        if structure.get("total_chunks", 0) == 0:
            critical_issues.append("No chunks found in index")
        
        if semantic.get("success_rate", 0) < 50:
            critical_issues.append("Low semantic search success rate")
        
        if structure.get("orphan_chunks"):
            warnings.append(f"{len(structure['orphan_chunks'])} orphan chunks")
        
        if critical_issues:
            report.append("STATUS: CRITICAL ISSUES FOUND")
            for issue in critical_issues:
                report.append(f"  [CRITICAL] {issue}")
        elif warnings:
            report.append("STATUS: VALIDATION PASSED WITH WARNINGS")
            for warning in warnings:
                report.append(f"  [WARNING] {warning}")
        else:
            report.append("STATUS: VALIDATION PASSED")
        
        report.append("")
        report.append("=" * 80)
        
        return "\n".join(report)
    
    def save_validation_data(self) -> str:
        """
        Save all validation data to JSON
        """
        validation_data = {
            "timestamp": datetime.now().isoformat(),
            "index_name": self.index_name,
            "structure": self.validate_chunk_structure(),
            "semantic_search": self.test_semantic_search(),
            "vector_search": self.test_vector_search(),
            "filtering": self.test_filtering(),
            "data_quality": self.check_data_quality()
        }
        
        filename = f"chunk_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(validation_data, f, indent=2, ensure_ascii=False, default=str)
        
        return filename

def main():
    """
    Main validation process
    """
    print("\n" + "=" * 80)
    print("SEMANTIC CHUNK VALIDATOR")
    print("=" * 80)
    
    validator = ChunkValidator()
    
    print("\nRunning validation tests...")
    print("This may take a few minutes depending on index size.\n")
    
    # Generate report
    report = validator.generate_report()
    print(report)
    
    # Save report to file
    report_file = f"chunk_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport saved to: {report_file}")
    
    # Save detailed validation data
    data_file = validator.save_validation_data()
    print(f"Detailed data saved to: {data_file}")
    
    return 0

if __name__ == "__main__":
    exit(main())