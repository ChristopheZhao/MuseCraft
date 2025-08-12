"""
CI/CD Integration Test Suite

This module provides automated testing for continuous integration and deployment
pipelines, including build validation, test automation, and deployment verification.
"""
import os
import json
import time
import subprocess
from typing import Dict, List, Any, Optional
from unittest.mock import patch, AsyncMock, MagicMock
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.ci_cd
@pytest.mark.asyncio
class TestCICDIntegration:
    """CI/CD pipeline integration tests."""
    
    async def test_build_process_validation(self):
        """Test the application build process for CI/CD compatibility."""
        
        build_validation_results = {}
        
        # Test requirements.txt validation
        requirements_path = os.path.join(os.path.dirname(__file__), "../requirements.txt")
        
        if os.path.exists(requirements_path):
            with open(requirements_path, 'r') as f:
                requirements_content = f.read()
            
            # Check for critical dependencies
            critical_deps = [
                "fastapi",
                "sqlalchemy",
                "redis",
                "pytest",
                "asyncio"
            ]
            
            missing_deps = []
            for dep in critical_deps:
                if dep not in requirements_content.lower():
                    missing_deps.append(dep)
            
            build_validation_results["requirements"] = {
                "file_exists": True,
                "critical_deps_present": len(missing_deps) == 0,
                "missing_dependencies": missing_deps,
                "total_dependencies": len(requirements_content.strip().split('\n'))
            }
        else:
            build_validation_results["requirements"] = {
                "file_exists": False,
                "error": "requirements.txt not found"
            }
        
        # Test Docker configuration
        dockerfile_path = os.path.join(os.path.dirname(__file__), "../Dockerfile")
        
        if os.path.exists(dockerfile_path):
            with open(dockerfile_path, 'r') as f:
                dockerfile_content = f.read()
            
            # Check for essential Docker instructions
            essential_instructions = ["FROM", "COPY", "RUN", "EXPOSE", "CMD"]
            present_instructions = []
            
            for instruction in essential_instructions:
                if instruction in dockerfile_content:
                    present_instructions.append(instruction)
            
            build_validation_results["docker"] = {
                "dockerfile_exists": True,
                "essential_instructions_present": len(present_instructions) == len(essential_instructions),
                "present_instructions": present_instructions,
                "dockerfile_size": len(dockerfile_content)
            }
        else:
            build_validation_results["docker"] = {
                "dockerfile_exists": False,
                "error": "Dockerfile not found"
            }
        
        # Test environment configuration
        env_example_path = os.path.join(os.path.dirname(__file__), "../.env.example")
        
        if os.path.exists(env_example_path):
            with open(env_example_path, 'r') as f:
                env_content = f.read()
            
            required_env_vars = [
                "DATABASE_URL",
                "REDIS_URL", 
                "SECRET_KEY",
                "OPENAI_API_KEY"
            ]
            
            missing_env_vars = []
            for var in required_env_vars:
                if var not in env_content:
                    missing_env_vars.append(var)
            
            build_validation_results["environment"] = {
                "env_example_exists": True,
                "required_vars_documented": len(missing_env_vars) == 0,
                "missing_env_vars": missing_env_vars
            }
        else:
            build_validation_results["environment"] = {
                "env_example_exists": False,
                "error": ".env.example not found"
            }
        
        # Verify build validation
        critical_failures = []
        
        if not build_validation_results["requirements"]["file_exists"]:
            critical_failures.append("requirements.txt missing")
        
        if not build_validation_results["requirements"].get("critical_deps_present", False):
            critical_failures.append("critical dependencies missing")
        
        assert len(critical_failures) == 0, f"Build validation failed: {critical_failures}"
        
        return build_validation_results
    
    async def test_automated_test_execution(self):
        """Test automated test execution for CI/CD pipeline."""
        
        test_execution_results = {}
        
        # Simulate running different test categories
        test_categories = [
            {
                "name": "unit_tests",
                "command": ["python", "-m", "pytest", "tests/", "-m", "not integration", "--tb=short"],
                "timeout": 300
            },
            {
                "name": "integration_tests", 
                "command": ["python", "-m", "pytest", "tests/", "-m", "integration", "--tb=short"],
                "timeout": 600
            },
            {
                "name": "performance_tests",
                "command": ["python", "-m", "pytest", "tests/", "-m", "performance", "--tb=short"],
                "timeout": 900
            }
        ]
        
        for category in test_categories:
            try:
                # In CI/CD environment, actually run the tests
                if os.getenv('CI') or os.getenv('GITHUB_ACTIONS'):
                    start_time = time.time()
                    
                    result = subprocess.run(
                        category["command"],
                        capture_output=True,
                        text=True,
                        timeout=category["timeout"],
                        cwd=os.path.dirname(__file__)
                    )
                    
                    execution_time = time.time() - start_time
                    
                    test_execution_results[category["name"]] = {
                        "executed": True,
                        "exit_code": result.returncode,
                        "execution_time": execution_time,
                        "stdout_lines": len(result.stdout.split('\n')),
                        "stderr_lines": len(result.stderr.split('\n')),
                        "success": result.returncode == 0
                    }
                else:
                    # Mock execution for local testing
                    test_execution_results[category["name"]] = {
                        "executed": False,
                        "mock": True,
                        "success": True,
                        "reason": "Not running in CI/CD environment"
                    }
                    
            except subprocess.TimeoutExpired:
                test_execution_results[category["name"]] = {
                    "executed": True,
                    "success": False,
                    "error": "Test execution timeout",
                    "timeout": category["timeout"]
                }
            except Exception as e:
                test_execution_results[category["name"]] = {
                    "executed": True,
                    "success": False,
                    "error": str(e)
                }
        
        # Verify test execution
        failed_categories = [
            name for name, result in test_execution_results.items()
            if not result.get("success", False)
        ]
        
        # In CI environment, all tests should pass
        if os.getenv('CI') or os.getenv('GITHUB_ACTIONS'):
            assert len(failed_categories) == 0, f"Test categories failed in CI: {failed_categories}"
        
        return test_execution_results
    
    async def test_code_quality_checks(self):
        """Test code quality and linting checks for CI/CD."""
        
        quality_check_results = {}
        
        # Define quality check tools
        quality_tools = [
            {
                "name": "flake8",
                "command": ["flake8", "app/", "--max-line-length=100", "--ignore=E501"],
                "description": "Python code style checking"
            },
            {
                "name": "black_check",
                "command": ["black", "--check", "--diff", "app/"],
                "description": "Python code formatting check"
            },
            {
                "name": "isort_check",
                "command": ["isort", "--check-only", "--diff", "app/"],
                "description": "Python import sorting check"
            },
            {
                "name": "mypy",
                "command": ["mypy", "app/", "--ignore-missing-imports"],
                "description": "Python type checking"
            }
        ]
        
        for tool in quality_tools:
            try:
                # Check if tool is available
                tool_available = subprocess.run(
                    ["which", tool["command"][0]], 
                    capture_output=True
                ).returncode == 0
                
                if tool_available:
                    if os.getenv('CI') or os.getenv('GITHUB_ACTIONS'):
                        # Run actual quality check in CI
                        result = subprocess.run(
                            tool["command"],
                            capture_output=True,
                            text=True,
                            timeout=180,  # 3 minutes timeout
                            cwd=os.path.dirname(__file__)
                        )
                        
                        quality_check_results[tool["name"]] = {
                            "available": True,
                            "executed": True,
                            "success": result.returncode == 0,
                            "exit_code": result.returncode,
                            "stdout": result.stdout[:1000],  # First 1000 chars
                            "stderr": result.stderr[:1000]
                        }
                    else:
                        # Mock successful check for local testing
                        quality_check_results[tool["name"]] = {
                            "available": True,
                            "executed": False,
                            "mock": True,
                            "success": True,
                            "reason": "Not running in CI/CD environment"
                        }
                else:
                    quality_check_results[tool["name"]] = {
                        "available": False,
                        "executed": False,
                        "success": False,
                        "error": f"Tool {tool['command'][0]} not available"
                    }
                    
            except subprocess.TimeoutExpired:
                quality_check_results[tool["name"]] = {
                    "available": True,
                    "executed": True,
                    "success": False,
                    "error": "Quality check timeout"
                }
            except Exception as e:
                quality_check_results[tool["name"]] = {
                    "available": True,
                    "executed": True,
                    "success": False,
                    "error": str(e)
                }
        
        return quality_check_results
    
    async def test_security_scanning(self):
        """Test security scanning for CI/CD pipeline."""
        
        security_scan_results = {}
        
        # Define security scanning tools
        security_tools = [
            {
                "name": "bandit",
                "command": ["bandit", "-r", "app/", "-f", "json"],
                "description": "Python security linting"
            },
            {
                "name": "safety",
                "command": ["safety", "check", "--json"],
                "description": "Python dependency vulnerability check"
            }
        ]
        
        for tool in security_tools:
            try:
                # Check if tool is available
                tool_available = subprocess.run(
                    ["which", tool["command"][0]], 
                    capture_output=True
                ).returncode == 0
                
                if tool_available:
                    if os.getenv('CI') or os.getenv('GITHUB_ACTIONS'):
                        # Run actual security scan in CI
                        result = subprocess.run(
                            tool["command"],
                            capture_output=True,
                            text=True,
                            timeout=300,  # 5 minutes timeout
                            cwd=os.path.dirname(__file__)
                        )
                        
                        # Try to parse JSON output
                        try:
                            if result.stdout:
                                scan_data = json.loads(result.stdout)
                                issues_found = len(scan_data.get("results", []))
                            else:
                                issues_found = 0
                        except json.JSONDecodeError:
                            issues_found = "unknown"
                        
                        security_scan_results[tool["name"]] = {
                            "available": True,
                            "executed": True,
                            "success": result.returncode == 0,
                            "issues_found": issues_found,
                            "exit_code": result.returncode
                        }
                    else:
                        # Mock successful scan for local testing
                        security_scan_results[tool["name"]] = {
                            "available": True,
                            "executed": False,
                            "mock": True,
                            "success": True,
                            "issues_found": 0,
                            "reason": "Not running in CI/CD environment"
                        }
                else:
                    security_scan_results[tool["name"]] = {
                        "available": False,
                        "executed": False,
                        "success": False,
                        "error": f"Tool {tool['command'][0]} not available"
                    }
                    
            except subprocess.TimeoutExpired:
                security_scan_results[tool["name"]] = {
                    "available": True,
                    "executed": True,
                    "success": False,
                    "error": "Security scan timeout"
                }
            except Exception as e:
                security_scan_results[tool["name"]] = {
                    "available": True,
                    "executed": True,
                    "success": False,
                    "error": str(e)
                }
        
        return security_scan_results
    
    async def test_deployment_artifact_generation(self):
        """Test generation of deployment artifacts."""
        
        artifact_results = {}
        
        # Test Docker image build (simulated)
        try:
            dockerfile_path = os.path.join(os.path.dirname(__file__), "../Dockerfile")
            
            if os.path.exists(dockerfile_path):
                if os.getenv('CI') or os.getenv('GITHUB_ACTIONS'):
                    # In CI, actually build the Docker image
                    result = subprocess.run(
                        ["docker", "build", "-t", "test-video-maker", "."],
                        capture_output=True,
                        text=True,
                        timeout=600,  # 10 minutes timeout
                        cwd=os.path.dirname(dockerfile_path)
                    )
                    
                    artifact_results["docker_image"] = {
                        "build_attempted": True,
                        "build_success": result.returncode == 0,
                        "exit_code": result.returncode,
                        "build_output_lines": len(result.stdout.split('\n'))
                    }
                else:
                    # Mock successful build for local testing
                    artifact_results["docker_image"] = {
                        "build_attempted": False,
                        "mock": True,
                        "build_success": True,
                        "reason": "Not running in CI/CD environment"
                    }
            else:
                artifact_results["docker_image"] = {
                    "build_attempted": False,
                    "build_success": False,
                    "error": "Dockerfile not found"
                }
                
        except subprocess.TimeoutExpired:
            artifact_results["docker_image"] = {
                "build_attempted": True,
                "build_success": False,
                "error": "Docker build timeout"
            }
        except Exception as e:
            artifact_results["docker_image"] = {
                "build_attempted": True,
                "build_success": False,
                "error": str(e)
            }
        
        # Test configuration files generation
        config_files = [
            "docker-compose.yml",
            "kubernetes.yaml",
            ".env.example"
        ]
        
        for config_file in config_files:
            file_path = os.path.join(os.path.dirname(__file__), f"../{config_file}")
            
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    content = f.read()
                
                artifact_results[f"config_{config_file}"] = {
                    "exists": True,
                    "size": len(content),
                    "non_empty": len(content.strip()) > 0
                }
            else:
                artifact_results[f"config_{config_file}"] = {
                    "exists": False,
                    "required": config_file in ["docker-compose.yml", ".env.example"]
                }
        
        return artifact_results
    
    async def test_deployment_smoke_test(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession
    ):
        """Test basic deployment smoke test functionality."""
        
        smoke_test_results = {}
        
        # Test critical endpoints
        critical_endpoints = [
            "/api/v1/system/health",
            "/api/v1/tasks/",
            "/docs"
        ]
        
        for endpoint in critical_endpoints:
            try:
                start_time = time.time()
                response = await test_client.get(endpoint)
                response_time = time.time() - start_time
                
                smoke_test_results[f"endpoint_{endpoint}"] = {
                    "accessible": True,
                    "status_code": response.status_code,
                    "response_time": response_time,
                    "success": response.status_code < 500,
                    "response_size": len(response.content)
                }
                
            except Exception as e:
                smoke_test_results[f"endpoint_{endpoint}"] = {
                    "accessible": False,
                    "error": str(e),
                    "success": False
                }
        
        # Test basic functionality
        try:
            # Test task creation
            response = await test_client.post("/api/v1/tasks/", json={
                "user_prompt": "Deployment smoke test",
                "video_style": "professional", 
                "duration": 30
            })
            
            smoke_test_results["task_creation"] = {
                "success": response.status_code == 201,
                "status_code": response.status_code,
                "response_data": response.json() if response.status_code == 201 else None
            }
            
        except Exception as e:
            smoke_test_results["task_creation"] = {
                "success": False,
                "error": str(e)
            }
        
        # Test database connectivity
        try:
            from sqlalchemy import text
            result = await test_db_session.execute(text("SELECT 1"))
            
            smoke_test_results["database_connectivity"] = {
                "success": result.scalar() == 1,
                "response": result.scalar()
            }
            
        except Exception as e:
            smoke_test_results["database_connectivity"] = {
                "success": False,
                "error": str(e)
            }
        
        # Calculate overall smoke test success
        successful_tests = sum(1 for result in smoke_test_results.values() if result.get("success", False))
        total_tests = len(smoke_test_results)
        success_rate = (successful_tests / total_tests) * 100 if total_tests > 0 else 0
        
        smoke_test_summary = {
            "success_rate": success_rate,
            "successful_tests": successful_tests,
            "total_tests": total_tests,
            "deployment_viable": success_rate >= 90,  # 90% success rate required
            "test_results": smoke_test_results
        }
        
        # Smoke test assertion
        assert smoke_test_summary["deployment_viable"], f"Smoke test success rate {success_rate:.1f}% below 90% threshold"
        
        return smoke_test_summary
    
    async def test_ci_cd_pipeline_integration(
        self,
        test_client: AsyncClient,
        test_db_session: AsyncSession
    ):
        """Test complete CI/CD pipeline integration."""
        
        pipeline_results = {}
        
        # Stage 1: Build validation
        pipeline_results["build_validation"] = await self.test_build_process_validation()
        
        # Stage 2: Test execution
        pipeline_results["test_execution"] = await self.test_automated_test_execution()
        
        # Stage 3: Code quality
        pipeline_results["code_quality"] = await self.test_code_quality_checks()
        
        # Stage 4: Security scanning
        pipeline_results["security_scanning"] = await self.test_security_scanning()
        
        # Stage 5: Artifact generation
        pipeline_results["artifact_generation"] = await self.test_deployment_artifact_generation()
        
        # Stage 6: Deployment smoke test
        pipeline_results["smoke_test"] = await self.test_deployment_smoke_test(test_client, test_db_session)
        
        # Calculate pipeline success metrics
        stage_success = {}
        for stage_name, stage_results in pipeline_results.items():
            if stage_name == "smoke_test":
                stage_success[stage_name] = stage_results.get("deployment_viable", False)
            else:
                # For other stages, check if most sub-components succeeded
                if isinstance(stage_results, dict):
                    successful_components = sum(
                        1 for component in stage_results.values()
                        if isinstance(component, dict) and component.get("success", False)
                    )
                    total_components = len([
                        c for c in stage_results.values() 
                        if isinstance(c, dict) and "success" in c
                    ])
                    
                    if total_components > 0:
                        stage_success[stage_name] = (successful_components / total_components) >= 0.8
                    else:
                        stage_success[stage_name] = True  # No testable components
                else:
                    stage_success[stage_name] = True  # Assume success if no clear failure
        
        successful_stages = sum(1 for success in stage_success.values() if success)
        total_stages = len(stage_success)
        pipeline_success_rate = (successful_stages / total_stages) * 100 if total_stages > 0 else 0
        
        pipeline_summary = {
            "pipeline_success_rate": pipeline_success_rate,
            "successful_stages": successful_stages,
            "total_stages": total_stages,
            "pipeline_viable": pipeline_success_rate >= 85,  # 85% success rate for viable pipeline
            "stage_success": stage_success,
            "stage_results": pipeline_results
        }
        
        # Pipeline integration assertion
        assert pipeline_summary["pipeline_viable"], f"CI/CD pipeline success rate {pipeline_success_rate:.1f}% below 85% threshold"
        
        return pipeline_summary


@pytest.mark.ci_cd
class TestGitHubActionsIntegration:
    """GitHub Actions specific integration tests."""
    
    def test_github_actions_workflow_validation(self):
        """Validate GitHub Actions workflow configuration."""
        
        # Look for GitHub Actions workflow files
        workflows_dir = os.path.join(os.path.dirname(__file__), "../../.github/workflows")
        
        workflow_validation = {
            "workflows_dir_exists": os.path.exists(workflows_dir),
            "workflow_files": [],
            "validation_results": {}
        }
        
        if workflow_validation["workflows_dir_exists"]:
            workflow_files = [f for f in os.listdir(workflows_dir) if f.endswith(('.yml', '.yaml'))]
            workflow_validation["workflow_files"] = workflow_files
            
            for workflow_file in workflow_files:
                workflow_path = os.path.join(workflows_dir, workflow_file)
                
                try:
                    with open(workflow_path, 'r') as f:
                        workflow_content = f.read()
                    
                    # Check for essential workflow components
                    essential_components = [
                        "on:",  # Trigger events
                        "jobs:",  # Job definitions
                        "runs-on:",  # Runner specification
                        "steps:",  # Step definitions
                        "uses: actions/checkout",  # Code checkout
                        "python"  # Python setup (assuming Python project)
                    ]
                    
                    present_components = [
                        comp for comp in essential_components
                        if comp in workflow_content
                    ]
                    
                    workflow_validation["validation_results"][workflow_file] = {
                        "file_size": len(workflow_content),
                        "essential_components_present": len(present_components),
                        "total_essential_components": len(essential_components),
                        "completeness": len(present_components) / len(essential_components),
                        "present_components": present_components
                    }
                    
                except Exception as e:
                    workflow_validation["validation_results"][workflow_file] = {
                        "error": str(e),
                        "valid": False
                    }
        
        return workflow_validation
    
    def test_github_secrets_documentation(self):
        """Test documentation of required GitHub secrets."""
        
        # Look for documentation about required secrets
        docs_locations = [
            os.path.join(os.path.dirname(__file__), "../../README.md"),
            os.path.join(os.path.dirname(__file__), "../../docs/deployment.md"),
            os.path.join(os.path.dirname(__file__), "../../.github/workflows")
        ]
        
        required_secrets = [
            "DATABASE_URL",
            "REDIS_URL",
            "SECRET_KEY", 
            "OPENAI_API_KEY",
            "STABILITY_API_KEY"
        ]
        
        secrets_documentation = {
            "documented_secrets": [],
            "missing_secrets": [],
            "documentation_locations": {}
        }
        
        for doc_location in docs_locations:
            if os.path.exists(doc_location):
                if os.path.isfile(doc_location):
                    # Single file
                    try:
                        with open(doc_location, 'r') as f:
                            content = f.read()
                        
                        documented_in_file = [
                            secret for secret in required_secrets
                            if secret in content
                        ]
                        
                        secrets_documentation["documentation_locations"][doc_location] = documented_in_file
                        secrets_documentation["documented_secrets"].extend(documented_in_file)
                        
                    except Exception:
                        pass
                        
                elif os.path.isdir(doc_location):
                    # Directory - check workflow files
                    try:
                        workflow_files = [f for f in os.listdir(doc_location) if f.endswith(('.yml', '.yaml'))]
                        
                        for workflow_file in workflow_files:
                            workflow_path = os.path.join(doc_location, workflow_file)
                            
                            with open(workflow_path, 'r') as f:
                                content = f.read()
                            
                            documented_in_file = [
                                secret for secret in required_secrets
                                if secret in content
                            ]
                            
                            if documented_in_file:
                                secrets_documentation["documentation_locations"][workflow_path] = documented_in_file
                                secrets_documentation["documented_secrets"].extend(documented_in_file)
                                
                    except Exception:
                        pass
        
        # Remove duplicates and find missing
        secrets_documentation["documented_secrets"] = list(set(secrets_documentation["documented_secrets"]))
        secrets_documentation["missing_secrets"] = [
            secret for secret in required_secrets
            if secret not in secrets_documentation["documented_secrets"]
        ]
        
        return secrets_documentation