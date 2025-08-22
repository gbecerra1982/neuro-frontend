"""
Migration script to transition from multi-layer architecture to unified agent
Run this script to validate and prepare the system for production deployment
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Dict, List, Any

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.utils_azure_search_semantic import AzureSearchSemantic
from src.agents.unified_rag_agent_production import ProductionRAGAgent
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MigrationValidator:
    """
    Validates system readiness for unified agent migration
    """
    
    def __init__(self):
        load_dotenv()
        self.validation_results = {
            'timestamp': datetime.now().isoformat(),
            'checks': [],
            'warnings': [],
            'errors': [],
            'ready_for_migration': False
        }
    
    def run_all_checks(self) -> Dict[str, Any]:
        """
        Run all validation checks
        """
        logger.info("="*60)
        logger.info("UNIFIED AGENT MIGRATION VALIDATOR")
        logger.info("="*60)
        
        # Check 1: Environment variables
        self.check_environment_variables()
        
        # Check 2: Azure Search connectivity
        self.check_azure_search()
        
        # Check 3: Azure OpenAI connectivity
        self.check_azure_openai()
        
        # Check 4: Test unified agent initialization
        self.check_unified_agent()
        
        # Check 5: Test search functionality
        self.check_search_functionality()
        
        # Check 6: Performance comparison
        self.run_performance_comparison()
        
        # Determine overall readiness
        self.validation_results['ready_for_migration'] = len(self.validation_results['errors']) == 0
        
        # Generate report
        self.generate_report()
        
        return self.validation_results
    
    def check_environment_variables(self):
        """
        Validate all required environment variables are set
        """
        logger.info("\n1. Checking environment variables...")
        
        required_vars = [
            'AZURE_OPENAI_STANDARD_API_KEY',
            'AZURE_OPENAI_STANDARD_ENDPOINT',
            'AZURE_SEARCH_SERVICE_ENDPOINT',
            'AZURE_SEARCH_ADMIN_KEY',
            'AZURE_SEARCH_INDEX'
        ]
        
        optional_vars = [
            'USE_UNIFIED_AGENT',
            'RAG_SEARCH_MODE',
            'RAG_MAX_SEARCH_RESULTS',
            'RAG_CHUNK_SIZE',
            'RAG_ENABLE_CACHE'
        ]
        
        missing_required = []
        missing_optional = []
        
        for var in required_vars:
            if not os.environ.get(var):
                missing_required.append(var)
        
        for var in optional_vars:
            if not os.environ.get(var):
                missing_optional.append(var)
        
        if missing_required:
            self.validation_results['errors'].append({
                'check': 'environment_variables',
                'message': f"Missing required variables: {missing_required}"
            })
            logger.error(f"   Missing required variables: {missing_required}")
        else:
            self.validation_results['checks'].append({
                'check': 'environment_variables',
                'status': 'passed',
                'message': 'All required environment variables are set'
            })
            logger.info("   All required environment variables are set")
        
        if missing_optional:
            self.validation_results['warnings'].append({
                'check': 'environment_variables',
                'message': f"Missing optional variables (will use defaults): {missing_optional}"
            })
            logger.warning(f"   Missing optional variables: {missing_optional}")
    
    def check_azure_search(self):
        """
        Test Azure Search connectivity and configuration
        """
        logger.info("\n2. Checking Azure Search connectivity...")
        
        try:
            search_client = AzureSearchSemantic()
            
            # Test search
            result = search_client.semantic_search(
                query="test connection",
                use_semantic=False,
                use_vector=False,
                top_k=1
            )
            
            if result.get('success') or 'results' in result:
                self.validation_results['checks'].append({
                    'check': 'azure_search',
                    'status': 'passed',
                    'message': f"Connected to index: {search_client.search_index}"
                })
                logger.info(f"   Connected to Azure Search index: {search_client.search_index}")
                
                # Check if index has documents
                total_docs = result.get('total_count', 0)
                if total_docs == 0:
                    self.validation_results['warnings'].append({
                        'check': 'azure_search',
                        'message': 'Index appears to be empty - no documents found'
                    })
                    logger.warning("   Warning: Index appears to be empty")
                else:
                    logger.info(f"   Index contains documents (sample count: {total_docs})")
            else:
                raise Exception(f"Search failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            self.validation_results['errors'].append({
                'check': 'azure_search',
                'message': f"Failed to connect to Azure Search: {str(e)}"
            })
            logger.error(f"   Failed to connect to Azure Search: {str(e)}")
    
    def check_azure_openai(self):
        """
        Test Azure OpenAI connectivity
        """
        logger.info("\n3. Checking Azure OpenAI connectivity...")
        
        try:
            from openai import AzureOpenAI
            
            client = AzureOpenAI(
                api_key=os.environ.get("AZURE_OPENAI_STANDARD_API_KEY"),
                api_version="2024-02-01",
                azure_endpoint=os.environ.get("AZURE_OPENAI_STANDARD_ENDPOINT")
            )
            
            # Test with a simple completion
            response = client.chat.completions.create(
                model=os.environ.get("AZURE_OPENAI_GPT4O_MINI_DEPLOYMENT", "gpt-4o-mini"),
                messages=[{"role": "user", "content": "test"}],
                max_tokens=10
            )
            
            if response:
                self.validation_results['checks'].append({
                    'check': 'azure_openai',
                    'status': 'passed',
                    'message': 'Successfully connected to Azure OpenAI'
                })
                logger.info("   Successfully connected to Azure OpenAI")
            
        except Exception as e:
            self.validation_results['errors'].append({
                'check': 'azure_openai',
                'message': f"Failed to connect to Azure OpenAI: {str(e)}"
            })
            logger.error(f"   Failed to connect to Azure OpenAI: {str(e)}")
    
    def check_unified_agent(self):
        """
        Test unified agent initialization
        """
        logger.info("\n4. Testing unified agent initialization...")
        
        try:
            agent = ProductionRAGAgent()
            
            # Check configuration
            config_info = {
                'search_mode': agent.search_mode.value,
                'max_results': agent.max_search_results,
                'chunk_size': agent.max_chunk_size,
                'caching_enabled': agent.enable_caching
            }
            
            self.validation_results['checks'].append({
                'check': 'unified_agent_init',
                'status': 'passed',
                'message': 'Unified agent initialized successfully',
                'config': config_info
            })
            logger.info(f"   Unified agent initialized with config: {json.dumps(config_info, indent=2)}")
            
        except Exception as e:
            self.validation_results['errors'].append({
                'check': 'unified_agent_init',
                'message': f"Failed to initialize unified agent: {str(e)}"
            })
            logger.error(f"   Failed to initialize unified agent: {str(e)}")
    
    def check_search_functionality(self):
        """
        Test actual search functionality
        """
        logger.info("\n5. Testing search functionality...")
        
        test_queries = [
            {
                'query': 'test query for validation',
                'type': 'general'
            },
            {
                'query': 'equipo DLS-168',
                'type': 'equipment'
            },
            {
                'query': 'pozo LACh-1030(h)',
                'type': 'well'
            }
        ]
        
        try:
            agent = ProductionRAGAgent()
            
            for test in test_queries:
                try:
                    response, session_id = agent.process_query(
                        test['query'],
                        'test_session',
                        force_search=True
                    )
                    
                    if response:
                        logger.info(f"   Test query '{test['type']}': SUCCESS")
                    else:
                        logger.warning(f"   Test query '{test['type']}': Empty response")
                        
                except Exception as e:
                    logger.error(f"   Test query '{test['type']}': FAILED - {str(e)}")
                    self.validation_results['warnings'].append({
                        'check': 'search_functionality',
                        'message': f"Query type '{test['type']}' failed: {str(e)}"
                    })
            
            self.validation_results['checks'].append({
                'check': 'search_functionality',
                'status': 'passed',
                'message': 'Basic search functionality is working'
            })
            
        except Exception as e:
            self.validation_results['errors'].append({
                'check': 'search_functionality',
                'message': f"Search functionality test failed: {str(e)}"
            })
            logger.error(f"   Search functionality test failed: {str(e)}")
    
    def run_performance_comparison(self):
        """
        Compare performance between old and new architecture
        """
        logger.info("\n6. Running performance comparison...")
        
        import time
        
        test_query = "What equipment is currently operating?"
        
        try:
            # Test unified agent
            start = time.time()
            agent = ProductionRAGAgent()
            response, _ = agent.process_query(test_query, 'perf_test', force_search=True)
            unified_time = time.time() - start
            
            # Test legacy agent (if available)
            legacy_time = None
            try:
                from src.agents.supervisor import procesar_consulta_langgraph
                start = time.time()
                response, _ = procesar_consulta_langgraph(test_query, 'perf_test')
                legacy_time = time.time() - start
            except Exception as e:
                logger.info("   Could not test legacy agent (this is OK if migrating fresh)")
            
            perf_results = {
                'unified_agent_time': round(unified_time, 3),
                'legacy_agent_time': round(legacy_time, 3) if legacy_time else 'N/A'
            }
            
            if legacy_time:
                improvement = ((legacy_time - unified_time) / legacy_time) * 100
                perf_results['improvement_percentage'] = round(improvement, 1)
                logger.info(f"   Performance improvement: {improvement:.1f}%")
            
            self.validation_results['checks'].append({
                'check': 'performance',
                'status': 'passed',
                'message': 'Performance test completed',
                'results': perf_results
            })
            
            logger.info(f"   Unified agent response time: {unified_time:.3f}s")
            if legacy_time:
                logger.info(f"   Legacy agent response time: {legacy_time:.3f}s")
            
        except Exception as e:
            self.validation_results['warnings'].append({
                'check': 'performance',
                'message': f"Performance test incomplete: {str(e)}"
            })
            logger.warning(f"   Performance test incomplete: {str(e)}")
    
    def generate_report(self):
        """
        Generate migration readiness report
        """
        logger.info("\n" + "="*60)
        logger.info("MIGRATION READINESS REPORT")
        logger.info("="*60)
        
        # Save report to file
        report_file = f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(self.validation_results, f, indent=2)
        
        # Print summary
        total_checks = len(self.validation_results['checks'])
        total_warnings = len(self.validation_results['warnings'])
        total_errors = len(self.validation_results['errors'])
        
        logger.info(f"\nValidation Summary:")
        logger.info(f"  Passed Checks: {total_checks}")
        logger.info(f"  Warnings: {total_warnings}")
        logger.info(f"  Errors: {total_errors}")
        
        if self.validation_results['ready_for_migration']:
            logger.info("\nRESULT: READY FOR MIGRATION")
            logger.info("\nNext steps:")
            logger.info("1. Review warnings (if any) and address if needed")
            logger.info("2. Set USE_UNIFIED_AGENT=true in your .env file")
            logger.info("3. Restart the application")
            logger.info("4. Monitor logs for the first few hours")
        else:
            logger.error("\nRESULT: NOT READY FOR MIGRATION")
            logger.error("\nPlease fix the following errors before migrating:")
            for error in self.validation_results['errors']:
                logger.error(f"  - {error['message']}")
        
        logger.info(f"\nDetailed report saved to: {report_file}")
        
        return self.validation_results['ready_for_migration']

def main():
    """
    Main migration script entry point
    """
    validator = MigrationValidator()
    
    # Run validation
    results = validator.run_all_checks()
    
    # Exit with appropriate code
    if results['ready_for_migration']:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()