#!/usr/bin/env python3
"""
System validation script to check project readiness
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings


class SystemValidator:
    """Comprehensive system validation"""
    
    def __init__(self):
        self.logger = logging.getLogger("system_validator")
        logging.basicConfig(level=logging.INFO)
        self.validation_results = []
        
    def run_all_validations(self) -> Dict[str, Any]:
        """Run all system validations"""
        print("🚀 Starting System Validation...\n")
        
        results = {
            "overall_status": "UNKNOWN",
            "critical_issues": [],
            "warnings": [],
            "validations": {}
        }
        
        # Run validation categories
        validations = [
            ("Configuration", self._validate_configuration),
            ("Dependencies", self._validate_dependencies),
            ("Database", self._validate_database_setup),
            ("File System", self._validate_file_system),
            ("Agent Architecture", self._validate_agent_architecture),
            ("Tool System", self._validate_tool_system),
            ("Memory System", self._validate_memory_system),
            ("Prompt Templates", self._validate_prompt_templates),
            ("API Endpoints", self._validate_api_endpoints)
        ]
        
        for category, validator_func in validations:
            print(f"🔍 Validating {category}...")
            try:
                validation_result = validator_func()
                results["validations"][category] = validation_result
                
                if validation_result["status"] == "CRITICAL":
                    results["critical_issues"].extend(validation_result["issues"])
                elif validation_result["status"] == "WARNING":
                    results["warnings"].extend(validation_result["issues"])
                    
                print(f"   {'✅' if validation_result['status'] == 'PASS' else '⚠️' if validation_result['status'] == 'WARNING' else '❌'} {category}: {validation_result['status']}")
                
            except Exception as e:
                results["critical_issues"].append(f"{category} validation failed: {str(e)}")
                results["validations"][category] = {
                    "status": "CRITICAL",
                    "issues": [f"Validation error: {str(e)}"]
                }
                print(f"   ❌ {category}: CRITICAL - {str(e)}")
        
        # Determine overall status
        if results["critical_issues"]:
            results["overall_status"] = "CRITICAL"
        elif results["warnings"]:
            results["overall_status"] = "WARNING"
        else:
            results["overall_status"] = "PASS"
        
        self._print_summary(results)
        return results
    
    def _validate_configuration(self) -> Dict[str, Any]:
        """Validate configuration settings"""
        issues = []
        status = "PASS"
        
        # Check required environment variables
        required_vars = [
            "DATABASE_URL",
            "REDIS_URL",
            "SECRET_KEY"
        ]
        
        for var in required_vars:
            value = getattr(settings, var, None)
            if not value or value in ["your-secret-key-here", "change-me"]:
                issues.append(f"Missing or default value for {var}")
                status = "CRITICAL"
        
        # Check AI API keys (warnings only)
        ai_keys = [
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY", 
            "STABILITY_API_KEY",
            "RUNWAY_API_KEY"
        ]
        
        missing_ai_keys = []
        for key in ai_keys:
            if not getattr(settings, key, None):
                missing_ai_keys.append(key)
        
        if missing_ai_keys:
            issues.append(f"Missing AI API keys: {', '.join(missing_ai_keys)}")
            if status == "PASS":
                status = "WARNING"
        
        # Check file paths
        paths_to_check = [
            settings.UPLOAD_PATH,
            settings.GENERATED_PATH,
            settings.TEMP_PATH
        ]
        
        for path in paths_to_check:
            path_obj = Path(path)
            if not path_obj.parent.exists():
                issues.append(f"Parent directory doesn't exist: {path}")
                status = "CRITICAL"
        
        return {
            "status": status,
            "issues": issues,
            "details": {
                "required_vars_set": len(required_vars) - len([i for i in issues if "Missing or default" in i]),
                "ai_keys_available": len(ai_keys) - len(missing_ai_keys),
                "file_paths_valid": len([p for p in paths_to_check if Path(p).parent.exists()])
            }
        }
    
    def _validate_dependencies(self) -> Dict[str, Any]:
        """Validate Python dependencies"""
        issues = []
        status = "PASS"
        
        # Critical dependencies
        critical_deps = [
            "fastapi",
            "sqlalchemy", 
            "redis",
            "celery",
            "pydantic",
            "jinja2",
            "pyyaml"
        ]
        
        missing_critical = []
        for dep in critical_deps:
            try:
                __import__(dep)
            except ImportError:
                missing_critical.append(dep)
                
        if missing_critical:
            issues.append(f"Missing critical dependencies: {', '.join(missing_critical)}")
            status = "CRITICAL"
        
        # AI service dependencies (warnings)
        ai_deps = ["openai", "anthropic"]
        missing_ai = []
        for dep in ai_deps:
            try:
                __import__(dep)
            except ImportError:
                missing_ai.append(dep)
        
        if missing_ai:
            issues.append(f"Missing AI service dependencies: {', '.join(missing_ai)}")
            if status == "PASS":
                status = "WARNING"
        
        return {
            "status": status,
            "issues": issues,
            "details": {
                "critical_deps_available": len(critical_deps) - len(missing_critical),
                "ai_deps_available": len(ai_deps) - len(missing_ai)
            }
        }
    
    def _validate_database_setup(self) -> Dict[str, Any]:
        """Validate database setup"""
        issues = []
        status = "PASS"
        
        try:
            from app.core.database import engine, SessionLocal
            
            # Try to create a session
            with SessionLocal() as session:
                # Try a simple query
                result = session.execute("SELECT 1")
                if not result:
                    issues.append("Database connection test failed")
                    status = "CRITICAL"
                    
        except Exception as e:
            issues.append(f"Database connection failed: {str(e)}")
            status = "CRITICAL"
        
        # Check if models are importable
        try:
            from app.models import Task, Scene, Resource
        except ImportError as e:
            issues.append(f"Model import failed: {str(e)}")
            status = "CRITICAL"
        
        return {
            "status": status,
            "issues": issues,
            "details": {
                "connection_test": "PASS" if status != "CRITICAL" else "FAIL",
                "models_importable": "PASS" if "Model import failed" not in str(issues) else "FAIL"
            }
        }
    
    def _validate_file_system(self) -> Dict[str, Any]:
        """Validate file system setup"""
        issues = []
        status = "PASS"
        
        directories = [
            settings.UPLOAD_PATH,
            settings.GENERATED_PATH,
            settings.TEMP_PATH
        ]
        
        for directory in directories:
            dir_path = Path(directory)
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                
                # Test write permissions
                test_file = dir_path / "test_write.tmp"
                test_file.write_text("test")
                test_file.unlink()
                
            except Exception as e:
                issues.append(f"Directory {directory} not writable: {str(e)}")
                status = "CRITICAL"
        
        return {
            "status": status,
            "issues": issues,
            "details": {
                "directories_created": len([d for d in directories if Path(d).exists()]),
                "directories_writable": len(directories) - len(issues)
            }
        }
    
    def _validate_agent_architecture(self) -> Dict[str, Any]:
        """Validate agent architecture"""
        issues = []
        status = "PASS"
        
        try:
            # Test base agent import
            from app.agents.base import BaseAgent
            
            # Test tool registry
            from app.agents.tools.tool_registry import get_tool_registry
            registry = get_tool_registry()
            
            # Test memory manager
            from app.agents.memory.long_term.manager import MemoryManager
            memory_manager = MemoryManager()
            
            # Test template manager
            from app.agents.prompts.template_manager import get_template_manager
            template_manager = get_template_manager()
            
        except ImportError as e:
            issues.append(f"Agent architecture import failed: {str(e)}")
            status = "CRITICAL"
        except Exception as e:
            issues.append(f"Agent architecture initialization failed: {str(e)}")
            status = "CRITICAL"
        
        return {
            "status": status,
            "issues": issues,
            "details": {
                "base_agent_importable": "PASS" if status != "CRITICAL" else "FAIL",
                "tool_registry_available": "PASS" if status != "CRITICAL" else "FAIL",
                "memory_manager_available": "PASS" if status != "CRITICAL" else "FAIL",
                "template_manager_available": "PASS" if status != "CRITICAL" else "FAIL"
            }
        }
    
    def _validate_tool_system(self) -> Dict[str, Any]:
        """Validate tool system"""
        issues = []
        status = "PASS"
        
        try:
            from app.agents.tools.tool_registry import get_tool_registry
            from app.agents.tools.base_tool import BaseTool, AsyncTool
            
            registry = get_tool_registry()
            available_tools = registry.list_tools()
            
            if not available_tools:
                issues.append("No tools registered in tool registry")
                status = "WARNING"
                
            # Test OpenAI tool if available
            if "openai_client" in available_tools:
                try:
                    tool = registry.get_tool("openai_client")
                    capabilities = tool.get_available_actions()
                    if not capabilities:
                        issues.append("OpenAI tool has no capabilities")
                        status = "WARNING"
                except Exception as e:
                    issues.append(f"OpenAI tool test failed: {str(e)}")
                    status = "WARNING"
            
        except Exception as e:
            issues.append(f"Tool system validation failed: {str(e)}")
            status = "CRITICAL"
        
        return {
            "status": status,
            "issues": issues,
            "details": {
                "tools_available": len(available_tools) if 'available_tools' in locals() else 0,
                "tool_registry_functional": "PASS" if status != "CRITICAL" else "FAIL"
            }
        }
    
    def _validate_memory_system(self) -> Dict[str, Any]:
        """Validate memory system"""
        issues = []
        status = "PASS"
        
        try:
            from app.agents.memory.long_term.manager import MemoryManager
            from app.agents.memory.long_term.stores import MemoryItem, MemoryType, MemoryImportance
            
            # Test memory manager initialization
            memory_manager = MemoryManager(config={
                "enable_consolidation": False,  # Disable for testing
                "enable_cleanup": False
            })
            
            # Test basic memory operations (async)
            async def test_memory():
                try:
                    # Store memory
                    memory_id = await memory_manager.store_memory(
                        content="Test memory",
                        memory_type=MemoryType.SHORT_TERM,
                        importance=MemoryImportance.MEDIUM,
                        tags=["test"],
                        agent_id="test_agent"
                    )
                    
                    # Retrieve memory
                    retrieved = await memory_manager.retrieve_memory(memory_id)
                    if not retrieved:
                        issues.append("Memory retrieval failed")
                        return "CRITICAL"
                    
                    # Search memories
                    memories = await memory_manager.search_memories(
                        query="test",
                        agent_id="test_agent",
                        limit=1
                    )
                    if not memories:
                        issues.append("Memory search failed")
                        return "WARNING"
                    
                    return "PASS"
                    
                except Exception as e:
                    issues.append(f"Memory operations failed: {str(e)}")
                    return "CRITICAL"
            
            # Run async test
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            test_result = loop.run_until_complete(test_memory())
            loop.close()
            
            if test_result != "PASS":
                status = test_result
                
        except Exception as e:
            issues.append(f"Memory system initialization failed: {str(e)}")
            status = "CRITICAL"
        
        return {
            "status": status,
            "issues": issues,
            "details": {
                "memory_manager_functional": "PASS" if status != "CRITICAL" else "FAIL",
                "basic_operations_work": "PASS" if not issues else "FAIL"
            }
        }
    
    def _validate_prompt_templates(self) -> Dict[str, Any]:
        """Validate prompt template system"""
        issues = []
        status = "PASS"
        
        try:
            from app.agents.prompts.template_manager import get_template_manager
            
            template_manager = get_template_manager()
            available_templates = template_manager.list_templates()
            
            if not available_templates:
                issues.append("No prompt templates found")
                status = "WARNING"
            else:
                # Test template rendering
                for template_name in available_templates[:3]:  # Test first 3
                    try:
                        metadata = template_manager.get_template_metadata(template_name)
                        
                        # Create test variables
                        test_vars = {}
                        for var in metadata.variables:
                            test_vars[var] = f"test_{var}"
                        
                        # Test rendering
                        rendered = template_manager.render_template(template_name, test_vars)
                        if not rendered:
                            issues.append(f"Template {template_name} rendered empty")
                            status = "WARNING"
                            
                    except Exception as e:
                        issues.append(f"Template {template_name} rendering failed: {str(e)}")
                        status = "WARNING"
            
        except Exception as e:
            issues.append(f"Prompt template system failed: {str(e)}")
            status = "CRITICAL"
        
        return {
            "status": status,
            "issues": issues,
            "details": {
                "templates_available": len(available_templates) if 'available_templates' in locals() else 0,
                "template_manager_functional": "PASS" if status != "CRITICAL" else "FAIL"
            }
        }
    
    def _validate_api_endpoints(self) -> Dict[str, Any]:
        """Validate API endpoint definitions"""
        issues = []
        status = "PASS"
        
        try:
            from app.api.v1.api import api_router
            from app.main import app
            
            # Check if routes are registered
            routes = app.routes
            if not routes:
                issues.append("No routes registered")
                status = "CRITICAL"
            
            # Check for essential endpoints
            essential_endpoints = [
                "/api/v1/tasks",
                "/api/v1/files",
                "/ws"
            ]
            
            route_paths = [str(route.path) for route in routes if hasattr(route, 'path')]
            
            missing_endpoints = []
            for endpoint in essential_endpoints:
                if not any(endpoint in path for path in route_paths):
                    missing_endpoints.append(endpoint)
            
            if missing_endpoints:
                issues.append(f"Missing essential endpoints: {', '.join(missing_endpoints)}")
                status = "WARNING"
                
        except Exception as e:
            issues.append(f"API endpoint validation failed: {str(e)}")
            status = "CRITICAL"
        
        return {
            "status": status,
            "issues": issues,
            "details": {
                "routes_registered": len(routes) if 'routes' in locals() else 0,
                "essential_endpoints_available": len(essential_endpoints) - len(missing_endpoints) if 'missing_endpoints' in locals() else 0
            }
        }
    
    def _print_summary(self, results: Dict[str, Any]):
        """Print validation summary"""
        print("\n" + "="*60)
        print("📊 SYSTEM VALIDATION SUMMARY")
        print("="*60)
        
        status_emoji = {
            "PASS": "✅",
            "WARNING": "⚠️", 
            "CRITICAL": "❌"
        }
        
        print(f"\n{status_emoji[results['overall_status']]} Overall Status: {results['overall_status']}")
        
        if results["critical_issues"]:
            print(f"\n🚨 Critical Issues ({len(results['critical_issues'])}):")
            for issue in results["critical_issues"]:
                print(f"   • {issue}")
        
        if results["warnings"]:
            print(f"\n⚠️ Warnings ({len(results['warnings'])}):")
            for warning in results["warnings"]:
                print(f"   • {warning}")
        
        print(f"\n📈 Validation Details:")
        for category, result in results["validations"].items():
            emoji = status_emoji[result["status"]]
            print(f"   {emoji} {category}: {result['status']}")
            if result.get("details"):
                for key, value in result["details"].items():
                    print(f"      - {key}: {value}")
        
        # Recommendations
        print(f"\n💡 Next Steps:")
        if results["overall_status"] == "CRITICAL":
            print("   1. Fix critical issues before attempting to start the application")
            print("   2. Ensure all required dependencies are installed")
            print("   3. Verify configuration settings")
        elif results["overall_status"] == "WARNING":
            print("   1. Application should start but some features may not work")
            print("   2. Consider fixing warnings for full functionality")
            print("   3. Add missing API keys for AI services")
        else:
            print("   1. System is ready for startup!")
            print("   2. Run: python -m app.main")
            print("   3. Access API at: http://localhost:8000")
        
        print("="*60)


def main():
    """Main validation function"""
    validator = SystemValidator()
    results = validator.run_all_validations()
    
    # Exit with appropriate code
    if results["overall_status"] == "CRITICAL":
        sys.exit(1)
    elif results["overall_status"] == "WARNING":
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
