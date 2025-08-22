"""
Test script for Agentic Retrieval implementation
Validates query planning, parallel execution, and result synthesis
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Any
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.agentic_retrieval_client import AgenticRetrievalClient
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AgenticRetrievalTester:
    """
    Comprehensive test suite for Agentic Retrieval
    """
    
    def __init__(self):
        self.client = AgenticRetrievalClient()
        self.test_results = []
    
    async def test_simple_query(self) -> Dict[str, Any]:
        """
        Test simple single-faceted query
        """
        logger.info("\n" + "="*60)
        logger.info("TEST 1: Simple Query")
        logger.info("="*60)
        
        query = "equipo DLS-168 ubicacion"
        
        start_time = datetime.now()
        results = await self.client.agentic_search(
            query=query,
            top_k=5
        )
        execution_time = (datetime.now() - start_time).total_seconds()
        
        test_result = {
            "test_name": "Simple Query",
            "query": query,
            "execution_time": execution_time,
            "documents_found": len(results.get("documents", [])),
            "semantic_answers": len(results.get("semantic_answers", [])),
            "subqueries_executed": results.get("metadata", {}).get("subqueries_executed", 0)
        }
        
        # Print results
        print(f"\nQuery: {query}")
        print(f"Execution time: {execution_time:.2f}s")
        print(f"Documents found: {test_result['documents_found']}")
        print(f"Subqueries executed: {test_result['subqueries_executed']}")
        
        if results.get("documents"):
            print("\nTop 3 Results:")
            for i, doc in enumerate(results["documents"][:3], 1):
                print(f"\n{i}. Chunk ID: {doc.get('chunk_id')}")
                print(f"   Headers: {doc.get('headers', {}).get('h1')} > {doc.get('headers', {}).get('h2')}")
                print(f"   Content: {doc.get('content', '')[:150]}...")
                print(f"   Score: {doc.get('combined_score', 0):.3f}")
        
        self.test_results.append(test_result)
        return test_result
    
    async def test_complex_multi_faceted_query(self) -> Dict[str, Any]:
        """
        Test complex query with multiple information needs
        """
        logger.info("\n" + "="*60)
        logger.info("TEST 2: Complex Multi-Faceted Query")
        logger.info("="*60)
        
        query = "Mostrame la ubicacion del equipo DLS-168, problemas operacionales del pozo LACh-1030 en la ultima semana, y datos de produccion del yacimiento Vaca Muerta"
        
        start_time = datetime.now()
        results = await self.client.agentic_search(
            query=query,
            top_k=10
        )
        execution_time = (datetime.now() - start_time).total_seconds()
        
        test_result = {
            "test_name": "Complex Multi-Faceted Query",
            "query": query[:100] + "...",
            "execution_time": execution_time,
            "documents_found": len(results.get("documents", [])),
            "semantic_answers": len(results.get("semantic_answers", [])),
            "subqueries_executed": results.get("metadata", {}).get("subqueries_executed", 0)
        }
        
        # Print results
        print(f"\nQuery: {query[:100]}...")
        print(f"Execution time: {execution_time:.2f}s")
        print(f"Documents found: {test_result['documents_found']}")
        print(f"Subqueries executed: {test_result['subqueries_executed']}")
        
        # Show subquery breakdown
        if "grounding_data" in results:
            subqueries = results["grounding_data"].get("subqueries_executed", [])
            if subqueries:
                print("\nSubqueries Generated:")
                for sq in subqueries:
                    print(f"  - Query: {sq.get('query', '')[:80]}...")
                    print(f"    Intent: {sq.get('intent', '')}")
                    print(f"    Documents: {sq.get('documents_found', 0)}")
        
        self.test_results.append(test_result)
        return test_result
    
    async def test_filtered_search(self) -> Dict[str, Any]:
        """
        Test search with metadata filters
        """
        logger.info("\n" + "="*60)
        logger.info("TEST 3: Filtered Search")
        logger.info("="*60)
        
        query = "problemas operacionales y novedades"
        filters = {
            "pozo": "LACh-1030(h)",
            "fecha": "2024-01-15"
        }
        
        start_time = datetime.now()
        results = await self.client.agentic_search(
            query=query,
            filters=filters,
            top_k=5
        )
        execution_time = (datetime.now() - start_time).total_seconds()
        
        test_result = {
            "test_name": "Filtered Search",
            "query": query,
            "filters": filters,
            "execution_time": execution_time,
            "documents_found": len(results.get("documents", [])),
            "semantic_answers": len(results.get("semantic_answers", [])),
            "subqueries_executed": results.get("metadata", {}).get("subqueries_executed", 0)
        }
        
        # Print results
        print(f"\nQuery: {query}")
        print(f"Filters: {json.dumps(filters, indent=2)}")
        print(f"Execution time: {execution_time:.2f}s")
        print(f"Documents found: {test_result['documents_found']}")
        
        # Verify filters were applied
        if results.get("documents"):
            print("\nVerifying filter application:")
            for doc in results["documents"][:3]:
                metadata = doc.get("metadata", {})
                print(f"  - Pozo: {metadata.get('pozo')}, Fecha: {metadata.get('fecha')}")
        
        self.test_results.append(test_result)
        return test_result
    
    async def test_conversational_context(self) -> Dict[str, Any]:
        """
        Test search with conversation history
        """
        logger.info("\n" + "="*60)
        logger.info("TEST 4: Conversational Context")
        logger.info("="*60)
        
        conversation_history = [
            {"role": "user", "content": "Que equipos estan operando en el yacimiento Vaca Muerta?"},
            {"role": "assistant", "content": "Los equipos DLS-168 y RIG-205 estan operando en Vaca Muerta."},
            {"role": "user", "content": "Cual es la ubicacion del primero?"}
        ]
        
        query = "y que problemas ha tenido en el ultimo mes?"
        
        start_time = datetime.now()
        results = await self.client.agentic_search(
            query=query,
            conversation_history=conversation_history,
            top_k=5
        )
        execution_time = (datetime.now() - start_time).total_seconds()
        
        test_result = {
            "test_name": "Conversational Context",
            "query": query,
            "has_context": True,
            "execution_time": execution_time,
            "documents_found": len(results.get("documents", [])),
            "semantic_answers": len(results.get("semantic_answers", [])),
            "subqueries_executed": results.get("metadata", {}).get("subqueries_executed", 0)
        }
        
        # Print results
        print(f"\nQuery: {query}")
        print(f"Context messages: {len(conversation_history)}")
        print(f"Execution time: {execution_time:.2f}s")
        print(f"Documents found: {test_result['documents_found']}")
        
        # Check if context was understood
        if "grounding_data" in results:
            subqueries = results["grounding_data"].get("subqueries_executed", [])
            if subqueries:
                print("\nContext Resolution in Subqueries:")
                for sq in subqueries[:2]:
                    print(f"  - {sq.get('query', '')[:100]}...")
        
        self.test_results.append(test_result)
        return test_result
    
    async def test_semantic_answers(self) -> Dict[str, Any]:
        """
        Test extraction of semantic answers
        """
        logger.info("\n" + "="*60)
        logger.info("TEST 5: Semantic Answer Extraction")
        logger.info("="*60)
        
        query = "cual es la profundidad actual de perforacion del pozo LACh-1030?"
        
        start_time = datetime.now()
        results = await self.client.agentic_search(
            query=query,
            top_k=5
        )
        execution_time = (datetime.now() - start_time).total_seconds()
        
        test_result = {
            "test_name": "Semantic Answer Extraction",
            "query": query,
            "execution_time": execution_time,
            "documents_found": len(results.get("documents", [])),
            "semantic_answers": len(results.get("semantic_answers", [])),
            "has_direct_answer": len(results.get("semantic_answers", [])) > 0
        }
        
        # Print results
        print(f"\nQuery: {query}")
        print(f"Execution time: {execution_time:.2f}s")
        print(f"Semantic answers found: {test_result['semantic_answers']}")
        
        if results.get("semantic_answers"):
            print("\nSemantic Answers:")
            for i, answer in enumerate(results["semantic_answers"], 1):
                print(f"\n{i}. Answer: {answer.get('text', '')}")
                print(f"   Score: {answer.get('score', 0):.3f}")
        
        self.test_results.append(test_result)
        return test_result
    
    async def test_performance_comparison(self) -> Dict[str, Any]:
        """
        Compare Agentic vs Standard search performance
        """
        logger.info("\n" + "="*60)
        logger.info("TEST 6: Performance Comparison")
        logger.info("="*60)
        
        query = "equipos operando en pozos con problemas de produccion"
        
        # Test Agentic Retrieval
        start_time = datetime.now()
        agentic_results = await self.client.agentic_search(
            query=query,
            top_k=10
        )
        agentic_time = (datetime.now() - start_time).total_seconds()
        
        # Test Fallback (standard) search
        start_time = datetime.now()
        standard_results = await self.client._fallback_search(
            query=query,
            filters=None,
            top_k=10
        )
        standard_time = (datetime.now() - start_time).total_seconds()
        
        test_result = {
            "test_name": "Performance Comparison",
            "query": query,
            "agentic_time": agentic_time,
            "standard_time": standard_time,
            "agentic_documents": len(agentic_results.get("documents", [])),
            "standard_documents": len(standard_results.get("documents", [])),
            "performance_improvement": f"{((standard_time - agentic_time) / standard_time * 100):.1f}%" if standard_time > 0 else "N/A"
        }
        
        # Print comparison
        print(f"\nQuery: {query}")
        print("\nPerformance Comparison:")
        print(f"  Agentic Retrieval:")
        print(f"    - Time: {agentic_time:.2f}s")
        print(f"    - Documents: {test_result['agentic_documents']}")
        print(f"    - Subqueries: {agentic_results.get('metadata', {}).get('subqueries_executed', 0)}")
        print(f"  Standard Search:")
        print(f"    - Time: {standard_time:.2f}s")
        print(f"    - Documents: {test_result['standard_documents']}")
        
        self.test_results.append(test_result)
        return test_result
    
    def generate_report(self) -> str:
        """
        Generate comprehensive test report
        """
        report = []
        report.append("\n" + "="*80)
        report.append("AGENTIC RETRIEVAL TEST REPORT")
        report.append("="*80)
        report.append(f"Timestamp: {datetime.now().isoformat()}")
        report.append(f"Tests Executed: {len(self.test_results)}")
        report.append("")
        
        # Summary statistics
        total_time = sum(r.get("execution_time", 0) for r in self.test_results)
        avg_time = total_time / len(self.test_results) if self.test_results else 0
        
        report.append("SUMMARY STATISTICS")
        report.append("-"*40)
        report.append(f"Total execution time: {total_time:.2f}s")
        report.append(f"Average query time: {avg_time:.2f}s")
        
        # Calculate average documents found
        docs_found = [r.get("documents_found", 0) for r in self.test_results if "documents_found" in r]
        if docs_found:
            report.append(f"Average documents per query: {sum(docs_found)/len(docs_found):.1f}")
        
        # Count tests with semantic answers
        with_answers = sum(1 for r in self.test_results if r.get("semantic_answers", 0) > 0)
        report.append(f"Tests with semantic answers: {with_answers}/{len(self.test_results)}")
        
        report.append("")
        report.append("INDIVIDUAL TEST RESULTS")
        report.append("-"*40)
        
        for result in self.test_results:
            report.append(f"\nTest: {result.get('test_name', 'Unknown')}")
            report.append(f"  Query: {result.get('query', '')[:80]}...")
            report.append(f"  Execution time: {result.get('execution_time', 0):.2f}s")
            report.append(f"  Documents found: {result.get('documents_found', 0)}")
            report.append(f"  Semantic answers: {result.get('semantic_answers', 0)}")
            
            if "filters" in result:
                report.append(f"  Filters applied: {json.dumps(result['filters'])}")
            
            if "performance_improvement" in result:
                report.append(f"  Performance vs standard: {result['performance_improvement']}")
        
        report.append("")
        report.append("RECOMMENDATIONS")
        report.append("-"*40)
        
        # Provide recommendations based on test results
        if avg_time > 4:
            report.append("- Consider reducing MAX_SUBQUERIES to improve response time")
        
        if with_answers < len(self.test_results) / 2:
            report.append("- Semantic answer extraction rate is low; check semantic configuration")
        
        # Check if agentic is faster than standard
        perf_test = next((r for r in self.test_results if r.get("test_name") == "Performance Comparison"), None)
        if perf_test and perf_test.get("agentic_time", 0) > perf_test.get("standard_time", 0):
            report.append("- Agentic retrieval is slower than standard; optimize query planning")
        
        report.append("")
        report.append("="*80)
        
        return "\n".join(report)
    
    async def run_all_tests(self):
        """
        Execute all tests
        """
        try:
            print("\n" + "="*80)
            print("STARTING AGENTIC RETRIEVAL TEST SUITE")
            print("="*80)
            
            # Run tests
            await self.test_simple_query()
            await self.test_complex_multi_faceted_query()
            await self.test_filtered_search()
            await self.test_conversational_context()
            await self.test_semantic_answers()
            await self.test_performance_comparison()
            
            # Generate report
            report = self.generate_report()
            print(report)
            
            # Save report to file
            report_file = f"agentic_retrieval_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"\nReport saved to: {report_file}")
            
            # Save detailed results to JSON
            results_file = f"agentic_retrieval_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(results_file, "w", encoding="utf-8") as f:
                json.dump(self.test_results, f, indent=2, default=str)
            print(f"Detailed results saved to: {results_file}")
            
        except Exception as e:
            logger.error(f"Test suite error: {e}", exc_info=True)
        
        finally:
            # Clean up
            self.client.close()

async def main():
    """
    Main test execution
    """
    tester = AgenticRetrievalTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    # Run tests
    asyncio.run(main())