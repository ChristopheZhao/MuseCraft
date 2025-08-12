#!/usr/bin/env python3
"""
Integration Test Runner and Report Generator

This script orchestrates the execution of the comprehensive integration test suite
and generates detailed reports for validation and deployment readiness.
"""
import asyncio
import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
import subprocess
import logging

# Add backend to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tests.conftest import *


class IntegrationTestRunner:
    """Comprehensive integration test runner."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.results = {}
        self.start_time = None
        self.end_time = None
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('integration_test_results.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all integration test suites."""
        
        self.start_time = time.time()
        self.logger.info("Starting comprehensive integration test suite")
        
        # Test suite configuration
        test_suites = [
            {
                "name": "end_to_end_workflow",
                "module": "test_comprehensive_e2e_workflow",
                "priority": "high",
                "timeout": 1800  # 30 minutes
            },
            {
                "name": "system_integration",
                "module": "test_system_integration_validation", 
                "priority": "high",
                "timeout": 1200  # 20 minutes
            },
            {
                "name": "performance_benchmarks",
                "module": "test_performance_benchmarks",
                "priority": "high",
                "timeout": 2400  # 40 minutes
            },
            {
                "name": "error_scenarios",
                "module": "test_error_scenarios_and_recovery",
                "priority": "medium",
                "timeout": 1800  # 30 minutes
            },
            {
                "name": "deployment_validation",
                "module": "test_deployment_validation",
                "priority": "high",
                "timeout": 900  # 15 minutes
            },
            {
                "name": "monitoring_health_checks",
                "module": "test_monitoring_and_health_checks",
                "priority": "medium",
                "timeout": 600  # 10 minutes
            },
            {
                "name": "ci_cd_integration",
                "module": "test_ci_cd_integration",
                "priority": "medium", 
                "timeout": 900  # 15 minutes
            }
        ]
        
        # Run test suites based on configuration
        selected_suites = self._select_test_suites(test_suites)
        
        for suite in selected_suites:
            await self._run_test_suite(suite)
        
        self.end_time = time.time()
        
        # Generate comprehensive report
        final_report = self._generate_final_report()
        
        return final_report
    
    def _select_test_suites(self, test_suites: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Select test suites based on configuration."""
        
        if self.config.get("run_all", False):
            return test_suites
        
        if self.config.get("priority_filter"):
            priority = self.config["priority_filter"]
            return [suite for suite in test_suites if suite["priority"] == priority]
        
        if self.config.get("suite_filter"):
            suite_names = self.config["suite_filter"]
            return [suite for suite in test_suites if suite["name"] in suite_names]
        
        # Default: run high priority suites
        return [suite for suite in test_suites if suite["priority"] == "high"]
    
    async def _run_test_suite(self, suite: Dict[str, Any]):
        """Run a single test suite."""
        
        suite_name = suite["name"]
        self.logger.info(f"Running test suite: {suite_name}")
        
        suite_start_time = time.time()
        
        try:
            # Build pytest command
            pytest_cmd = [
                "python", "-m", "pytest",
                f"tests/{suite['module']}.py",
                "-v",
                "--tb=short",
                "--json-report",
                f"--json-report-file=test_reports/{suite_name}_report.json"
            ]
            
            # Add markers if specified
            if self.config.get("markers"):
                for marker in self.config["markers"]:
                    pytest_cmd.extend(["-m", marker])
            
            # Run the test suite
            process = await asyncio.create_subprocess_exec(
                *pytest_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.path.dirname(__file__)
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=suite["timeout"]
                )
                
                suite_end_time = time.time()
                execution_time = suite_end_time - suite_start_time
                
                # Parse results
                suite_results = {
                    "name": suite_name,
                    "execution_time": execution_time,
                    "exit_code": process.returncode,
                    "success": process.returncode == 0,
                    "stdout": stdout.decode('utf-8', errors='ignore'),
                    "stderr": stderr.decode('utf-8', errors='ignore'),
                    "timeout": False
                }
                
                # Try to load JSON report if available
                json_report_path = f"test_reports/{suite_name}_report.json"
                if os.path.exists(json_report_path):
                    try:
                        with open(json_report_path, 'r') as f:
                            json_report = json.load(f)
                        suite_results["json_report"] = json_report
                    except Exception as e:
                        self.logger.warning(f"Could not load JSON report for {suite_name}: {e}")
                
                self.results[suite_name] = suite_results
                
                if suite_results["success"]:
                    self.logger.info(f"Test suite {suite_name} completed successfully in {execution_time:.2f}s")
                else:
                    self.logger.error(f"Test suite {suite_name} failed with exit code {process.returncode}")
                    
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                
                self.results[suite_name] = {
                    "name": suite_name,
                    "execution_time": suite["timeout"],
                    "success": False,
                    "timeout": True,
                    "error": f"Test suite timed out after {suite['timeout']} seconds"
                }
                
                self.logger.error(f"Test suite {suite_name} timed out after {suite['timeout']} seconds")
                
        except Exception as e:
            self.results[suite_name] = {
                "name": suite_name,
                "success": False,
                "error": str(e),
                "exception": True
            }
            
            self.logger.error(f"Exception running test suite {suite_name}: {e}")
    
    def _generate_final_report(self) -> Dict[str, Any]:
        """Generate comprehensive final report."""
        
        total_execution_time = (self.end_time - self.start_time) if self.end_time and self.start_time else 0
        
        # Calculate overall statistics
        total_suites = len(self.results)
        successful_suites = sum(1 for result in self.results.values() if result.get("success", False))
        failed_suites = total_suites - successful_suites
        
        # Calculate detailed statistics
        suite_statistics = {}
        for suite_name, result in self.results.items():
            if "json_report" in result:
                json_report = result["json_report"]
                suite_statistics[suite_name] = {
                    "tests_collected": json_report.get("summary", {}).get("collected", 0),
                    "tests_passed": json_report.get("summary", {}).get("passed", 0),
                    "tests_failed": json_report.get("summary", {}).get("failed", 0),
                    "tests_skipped": json_report.get("summary", {}).get("skipped", 0),
                    "duration": json_report.get("duration", 0)
                }
            else:
                suite_statistics[suite_name] = {
                    "tests_collected": "unknown",
                    "tests_passed": "unknown", 
                    "tests_failed": "unknown",
                    "tests_skipped": "unknown",
                    "duration": result.get("execution_time", 0)
                }
        
        # Generate recommendations
        recommendations = self._generate_recommendations()
        
        # Create final report
        final_report = {
            "test_execution_summary": {
                "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
                "end_time": datetime.fromtimestamp(self.end_time).isoformat(),
                "total_execution_time": total_execution_time,
                "total_suites": total_suites,
                "successful_suites": successful_suites,
                "failed_suites": failed_suites,
                "success_rate": (successful_suites / total_suites) * 100 if total_suites > 0 else 0
            },
            "suite_results": self.results,
            "suite_statistics": suite_statistics,
            "recommendations": recommendations,
            "deployment_readiness": {
                "ready": successful_suites >= (total_suites * 0.8),  # 80% success rate
                "readiness_score": (successful_suites / total_suites) * 100 if total_suites > 0 else 0,
                "critical_failures": [
                    name for name, result in self.results.items()
                    if not result.get("success", False) and name in ["deployment_validation", "system_integration"]
                ]
            },
            "generated_at": datetime.now().isoformat(),
            "configuration": self.config
        }
        
        return final_report
    
    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on test results."""
        
        recommendations = []
        
        # Check for failed critical suites
        critical_suites = ["deployment_validation", "system_integration", "end_to_end_workflow"]
        failed_critical = [
            name for name in critical_suites
            if name in self.results and not self.results[name].get("success", False)
        ]
        
        if failed_critical:
            recommendations.append(f"Critical test suites failed: {', '.join(failed_critical)}. Address these before deployment.")
        
        # Check for timeouts
        timed_out_suites = [
            name for name, result in self.results.items()
            if result.get("timeout", False)
        ]
        
        if timed_out_suites:
            recommendations.append(f"Test suites timed out: {', '.join(timed_out_suites)}. Consider increasing timeout or optimizing tests.")
        
        # Check for performance issues
        slow_suites = [
            name for name, result in self.results.items()
            if result.get("execution_time", 0) > 1800  # 30 minutes
        ]
        
        if slow_suites:
            recommendations.append(f"Slow test suites detected: {', '.join(slow_suites)}. Consider performance optimization.")
        
        # Success rate recommendations
        success_rate = len([r for r in self.results.values() if r.get("success", False)]) / len(self.results) * 100
        
        if success_rate < 50:
            recommendations.append("Low test success rate. System may not be ready for deployment.")
        elif success_rate < 80:
            recommendations.append("Moderate test success rate. Review failed tests before deployment.")
        elif success_rate >= 95:
            recommendations.append("Excellent test success rate. System appears ready for deployment.")
        
        return recommendations
    
    def save_report(self, report: Dict[str, Any], filename: str = None):
        """Save the final report to file."""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"integration_test_report_{timestamp}.json"
        
        # Ensure reports directory exists
        os.makedirs("test_reports", exist_ok=True)
        
        report_path = os.path.join("test_reports", filename)
        
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        self.logger.info(f"Integration test report saved to: {report_path}")
        
        # Also generate human-readable report
        html_report_path = report_path.replace('.json', '.html')
        self._generate_html_report(report, html_report_path)
        
        return report_path
    
    def _generate_html_report(self, report: Dict[str, Any], html_path: str):
        """Generate HTML report for better readability."""
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Integration Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
        .summary {{ margin: 20px 0; }}
        .suite {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
        .success {{ background-color: #d4edda; border-color: #c3e6cb; }}
        .failure {{ background-color: #f8d7da; border-color: #f5c6cb; }}
        .recommendations {{ background-color: #fff3cd; padding: 15px; border-radius: 5px; }}
        pre {{ background-color: #f8f9fa; padding: 10px; border-radius: 3px; overflow-x: auto; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Integration Test Report</h1>
        <p>Generated: {report['generated_at']}</p>
        <p>Total Execution Time: {report['test_execution_summary']['total_execution_time']:.2f} seconds</p>
    </div>
    
    <div class="summary">
        <h2>Test Execution Summary</h2>
        <ul>
            <li>Total Suites: {report['test_execution_summary']['total_suites']}</li>
            <li>Successful Suites: {report['test_execution_summary']['successful_suites']}</li>
            <li>Failed Suites: {report['test_execution_summary']['failed_suites']}</li>
            <li>Success Rate: {report['test_execution_summary']['success_rate']:.1f}%</li>
        </ul>
    </div>
    
    <div class="deployment-readiness">
        <h2>Deployment Readiness</h2>
        <p><strong>Ready for Deployment:</strong> {'✅ Yes' if report['deployment_readiness']['ready'] else '❌ No'}</p>
        <p><strong>Readiness Score:</strong> {report['deployment_readiness']['readiness_score']:.1f}%</p>
        {f"<p><strong>Critical Failures:</strong> {', '.join(report['deployment_readiness']['critical_failures'])}</p>" if report['deployment_readiness']['critical_failures'] else ""}
    </div>
    
    <div class="recommendations">
        <h2>Recommendations</h2>
        <ul>
            {''.join(f'<li>{rec}</li>' for rec in report['recommendations'])}
        </ul>
    </div>
    
    <div class="suite-results">
        <h2>Test Suite Results</h2>
        {''.join(self._generate_suite_html(name, result) for name, result in report['suite_results'].items())}
    </div>
    
</body>
</html>
"""
        
        with open(html_path, 'w') as f:
            f.write(html_content)
        
        self.logger.info(f"HTML report saved to: {html_path}")
    
    def _generate_suite_html(self, suite_name: str, result: Dict[str, Any]) -> str:
        """Generate HTML for a single test suite result."""
        
        success_class = "success" if result.get("success", False) else "failure"
        status_icon = "✅" if result.get("success", False) else "❌"
        
        return f"""
        <div class="suite {success_class}">
            <h3>{status_icon} {suite_name}</h3>
            <p><strong>Status:</strong> {'Success' if result.get('success', False) else 'Failed'}</p>
            <p><strong>Execution Time:</strong> {result.get('execution_time', 0):.2f} seconds</p>
            {f'<p><strong>Error:</strong> {result.get("error", "")}</p>' if result.get('error') else ''}
            {f'<p><strong>Timeout:</strong> Yes</p>' if result.get('timeout') else ''}
            
            {f'<details><summary>Standard Output</summary><pre>{result.get("stdout", "")}</pre></details>' if result.get('stdout') else ''}
            {f'<details><summary>Standard Error</summary><pre>{result.get("stderr", "")}</pre></details>' if result.get('stderr') else ''}
        </div>
        """


def main():
    """Main entry point for the integration test runner."""
    
    parser = argparse.ArgumentParser(description="Run comprehensive integration tests")
    parser.add_argument("--all", action="store_true", help="Run all test suites")
    parser.add_argument("--priority", choices=["high", "medium", "low"], help="Run tests by priority")
    parser.add_argument("--suites", nargs="+", help="Specific test suites to run")
    parser.add_argument("--markers", nargs="+", help="Pytest markers to include")
    parser.add_argument("--report-file", help="Custom report filename")
    parser.add_argument("--parallel", action="store_true", help="Run tests in parallel (experimental)")
    
    args = parser.parse_args()
    
    # Build configuration
    config = {
        "run_all": args.all,
        "priority_filter": args.priority,
        "suite_filter": args.suites,
        "markers": args.markers,
        "parallel": args.parallel
    }
    
    # If no specific selection made, run high priority tests
    if not any([args.all, args.priority, args.suites]):
        config["priority_filter"] = "high"
    
    # Create test reports directory
    os.makedirs("test_reports", exist_ok=True)
    
    # Run tests
    async def run_tests():
        runner = IntegrationTestRunner(config)
        report = await runner.run_all_tests()
        report_path = runner.save_report(report, args.report_file)
        
        # Print summary
        print("\n" + "="*80)
        print("INTEGRATION TEST EXECUTION SUMMARY")
        print("="*80)
        print(f"Total Suites: {report['test_execution_summary']['total_suites']}")
        print(f"Successful: {report['test_execution_summary']['successful_suites']}")
        print(f"Failed: {report['test_execution_summary']['failed_suites']}")
        print(f"Success Rate: {report['test_execution_summary']['success_rate']:.1f}%")
        print(f"Execution Time: {report['test_execution_summary']['total_execution_time']:.2f}s")
        print(f"Deployment Ready: {'Yes' if report['deployment_readiness']['ready'] else 'No'}")
        print(f"Report saved to: {report_path}")
        
        if report['recommendations']:
            print("\nRecommendations:")
            for rec in report['recommendations']:
                print(f"  • {rec}")
        
        print("="*80)
        
        # Exit with appropriate code
        if report['deployment_readiness']['ready']:
            return 0
        else:
            return 1
    
    # Run the async function
    try:
        exit_code = asyncio.run(run_tests())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nTest execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error running integration tests: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()