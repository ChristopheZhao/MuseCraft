#!/usr/bin/env python3
"""
短视频生成平台完整测试套件运行器
统一运行所有测试并生成综合报告
"""

import os
import sys
import time
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any
import subprocess
import concurrent.futures
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

class TestSuiteRunner:
    """测试套件运行器"""
    
    def __init__(self):
        self.test_results = {}
        self.start_time = None
        self.end_time = None
        
        # 测试套件配置
        self.test_suites = {
            "e2e": {
                "name": "端到端工作流测试",
                "module": "tests.e2e.test_complete_workflow",
                "function": "run_e2e_tests",
                "required": True,
                "timeout": 600  # 10分钟
            },
            "integration": {
                "name": "系统集成测试",
                "module": "tests.integration.test_system_integration",
                "function": "run_integration_tests",
                "required": True,
                "timeout": 300  # 5分钟
            },
            "ai_services": {
                "name": "AI服务集成测试",
                "module": "tests.ai_services.test_ai_integration",
                "function": "run_ai_integration_tests",
                "required": True,
                "timeout": 400  # 6分钟40秒
            },
            "performance": {
                "name": "性能和可靠性测试",
                "module": "tests.performance.test_performance_reliability", 
                "function": "run_performance_reliability_tests",
                "required": False,
                "timeout": 900  # 15分钟
            },
            "ux": {
                "name": "用户体验测试",
                "module": "tests.ux.test_user_experience",
                "function": "run_user_experience_tests",
                "required": False,
                "timeout": 300  # 5分钟
            }
        }
    
    def run_all_tests(self, test_types: List[str] = None, parallel: bool = False, 
                     mock_mode: bool = False, quick_mode: bool = False) -> bool:
        """
        运行所有测试套件
        
        Args:
            test_types: 要运行的测试类型列表，None表示运行所有
            parallel: 是否并行运行测试
            mock_mode: 是否使用模拟模式
            quick_mode: 是否使用快速模式（跳过长时间测试）
        """
        print("🚀 开始运行完整测试套件...")
        print(f"测试模式: {'模拟' if mock_mode else '真实'}")
        print(f"运行方式: {'并行' if parallel else '串行'}")
        print(f"测试模式: {'快速' if quick_mode else '完整'}")
        print("=" * 60)
        
        self.start_time = time.time()
        
        # 设置环境变量
        if mock_mode:
            os.environ["TEST_MODE"] = "mock"
        
        # 确定要运行的测试
        if test_types is None:
            test_types = list(self.test_suites.keys())
        
        if quick_mode:
            # 快速模式跳过性能测试
            test_types = [t for t in test_types if t != "performance"]
        
        # 验证服务可用性
        if not mock_mode:
            if not self._check_services_availability():
                print("❌ 服务不可用，请检查系统状态")
                return False
        
        success = True
        
        if parallel and len(test_types) > 1:
            success = self._run_tests_parallel(test_types)
        else:
            success = self._run_tests_sequential(test_types)
        
        self.end_time = time.time()
        
        # 生成综合报告
        self._generate_comprehensive_report()
        
        return success
    
    def _check_services_availability(self) -> bool:
        """检查必要服务的可用性"""
        print("🔍 检查服务可用性...")
        
        services = {
            "后端API": "http://localhost:8000/health",
            "前端服务": "http://localhost:3000",
            "数据库": "postgresql://localhost:5432",
            "Redis": "redis://localhost:6379"
        }
        
        available_services = 0
        
        for service_name, url in services.items():
            try:
                if url.startswith("http"):
                    import requests
                    response = requests.get(url, timeout=5)
                    available = response.status_code == 200
                elif url.startswith("postgresql"):
                    import psycopg2
                    conn = psycopg2.connect(
                        host="localhost",
                        port=5432,
                        user="user",
                        password="password",
                        database="short_video_maker"
                    )
                    conn.close()
                    available = True
                elif url.startswith("redis"):
                    import redis
                    client = redis.from_url(url)
                    available = client.ping()
                else:
                    available = False
                
                if available:
                    print(f"   ✅ {service_name} 可用")
                    available_services += 1
                else:
                    print(f"   ❌ {service_name} 不可用")
                    
            except Exception as e:
                print(f"   ❌ {service_name} 连接失败: {e}")
        
        # 至少需要后端API可用
        return available_services >= 1
    
    def _run_tests_sequential(self, test_types: List[str]) -> bool:
        """串行运行测试"""
        print("📋 串行运行测试套件...")
        
        overall_success = True
        
        for test_type in test_types:
            if test_type not in self.test_suites:
                print(f"⚠️ 未知测试类型: {test_type}")
                continue
            
            suite = self.test_suites[test_type]
            print(f"\n🧪 运行 {suite['name']}...")
            
            success = self._run_single_test(test_type)
            
            if not success:
                if suite["required"]:
                    print(f"❌ 必需测试 {suite['name']} 失败")
                    overall_success = False
                else:
                    print(f"⚠️ 可选测试 {suite['name']} 失败")
        
        return overall_success
    
    def _run_tests_parallel(self, test_types: List[str]) -> bool:
        """并行运行测试"""
        print("⚡ 并行运行测试套件...")
        
        overall_success = True
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # 提交所有测试任务
            future_to_test = {
                executor.submit(self._run_single_test, test_type): test_type
                for test_type in test_types
                if test_type in self.test_suites
            }
            
            # 收集结果
            for future in concurrent.futures.as_completed(future_to_test):
                test_type = future_to_test[future]
                suite = self.test_suites[test_type]
                
                try:
                    success = future.result()
                    
                    if not success:
                        if suite["required"]:
                            print(f"❌ 必需测试 {suite['name']} 失败")
                            overall_success = False
                        else:
                            print(f"⚠️ 可选测试 {suite['name']} 失败")
                    else:
                        print(f"✅ {suite['name']} 完成")
                        
                except Exception as e:
                    print(f"❌ {suite['name']} 执行异常: {e}")
                    if suite["required"]:
                        overall_success = False
        
        return overall_success
    
    def _run_single_test(self, test_type: str) -> bool:
        """运行单个测试套件"""
        suite = self.test_suites[test_type]
        
        start_time = time.time()
        
        try:
            # 动态导入测试模块
            module_path = suite["module"]
            function_name = suite["function"]
            
            # 使用subprocess运行测试，避免模块导入冲突
            test_file = str(project_root / suite["module"].replace(".", "/") + ".py")
            
            if not os.path.exists(test_file):
                raise FileNotFoundError(f"测试文件不存在: {test_file}")
            
            # 运行测试
            result = subprocess.run(
                [sys.executable, test_file],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=suite["timeout"]
            )
            
            execution_time = time.time() - start_time
            success = result.returncode == 0
            
            self.test_results[test_type] = {
                "name": suite["name"],
                "success": success,
                "execution_time": execution_time,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
                "required": suite["required"]
            }
            
            return success
            
        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            print(f"⏰ {suite['name']} 超时 ({suite['timeout']}s)")
            
            self.test_results[test_type] = {
                "name": suite["name"],
                "success": False,
                "execution_time": execution_time,
                "error": "测试超时",
                "timeout": True,
                "required": suite["required"]
            }
            
            return False
            
        except Exception as e:
            execution_time = time.time() - start_time
            print(f"❌ {suite['name']} 执行失败: {e}")
            
            self.test_results[test_type] = {
                "name": suite["name"],
                "success": False,
                "execution_time": execution_time,
                "error": str(e),
                "required": suite["required"]
            }
            
            return False
    
    def _generate_comprehensive_report(self):
        """生成综合测试报告"""
        print("\n" + "=" * 60)
        print("📊 生成综合测试报告...")
        
        total_time = self.end_time - self.start_time if self.end_time and self.start_time else 0
        total_tests = len(self.test_results)
        successful_tests = sum(1 for result in self.test_results.values() if result["success"])
        failed_tests = total_tests - successful_tests
        
        # 计算不同类型的测试结果
        required_tests = [r for r in self.test_results.values() if r.get("required", True)]
        optional_tests = [r for r in self.test_results.values() if not r.get("required", True)]
        
        required_passed = sum(1 for r in required_tests if r["success"])
        optional_passed = sum(1 for r in optional_tests if r["success"])
        
        # 控制台报告
        print(f"""
        =================== 综合测试报告 ===================
        测试开始时间: {datetime.fromtimestamp(self.start_time).strftime('%Y-%m-%d %H:%M:%S') if self.start_time else 'N/A'}
        测试结束时间: {datetime.fromtimestamp(self.end_time).strftime('%Y-%m-%d %H:%M:%S') if self.end_time else 'N/A'}
        总耗时: {total_time:.1f} 秒
        
        测试概览:
        总测试套件: {total_tests}
        成功: {successful_tests}
        失败: {failed_tests}
        成功率: {(successful_tests/total_tests*100):.1f}%
        
        必需测试: {len(required_tests)} (通过: {required_passed})
        可选测试: {len(optional_tests)} (通过: {optional_passed})
        
        详细结果:
        """)
        
        for test_type, result in self.test_results.items():
            status_icon = "✅" if result["success"] else "❌"
            required_marker = "[必需]" if result.get("required", True) else "[可选]"
            
            print(f"        {status_icon} {result['name']} {required_marker}")
            print(f"           耗时: {result['execution_time']:.1f}秒")
            
            if not result["success"]:
                if "error" in result:
                    print(f"           错误: {result['error']}")
                if result.get("timeout"):
                    print(f"           原因: 超时")
                if result.get("return_code", 0) != 0:
                    print(f"           返回码: {result['return_code']}")
        
        # 系统健康评估
        print(f"""
        
        系统健康评估:
        """)
        
        if required_passed == len(required_tests):
            if optional_passed >= len(optional_tests) * 0.8:
                health_status = "优秀"
                health_icon = "🎉"
                health_desc = "所有核心功能正常，系统运行状态优秀"
            else:
                health_status = "良好"
                health_icon = "👍"
                health_desc = "核心功能正常，部分可选功能需要优化"
        elif required_passed >= len(required_tests) * 0.8:
            health_status = "一般"
            health_icon = "⚠️"
            health_desc = "大部分核心功能正常，需要解决部分关键问题"
        else:
            health_status = "需要改进"
            health_icon = "🚨"
            health_desc = "存在重要功能问题，需要立即处理"
        
        print(f"        {health_icon} 系统健康状态: {health_status}")
        print(f"        {health_desc}")
        
        # 生成JSON报告
        self._save_json_report(total_time, health_status)
        
        # 生成HTML报告
        self._save_html_report(total_time, health_status, health_desc)
        
        print("        ===============================================")
    
    def _save_json_report(self, total_time: float, health_status: str):
        """保存JSON格式的测试报告"""
        report_data = {
            "test_run": {
                "start_time": self.start_time,
                "end_time": self.end_time,
                "total_time": total_time,
                "timestamp": datetime.now().isoformat()
            },
            "summary": {
                "total_tests": len(self.test_results),
                "successful_tests": sum(1 for r in self.test_results.values() if r["success"]),
                "failed_tests": sum(1 for r in self.test_results.values() if not r["success"]),
                "health_status": health_status
            },
            "test_results": self.test_results
        }
        
        report_file = project_root / "test_results" / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_file.parent.mkdir(exist_ok=True)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        print(f"        📄 JSON报告已保存: {report_file}")
    
    def _save_html_report(self, total_time: float, health_status: str, health_desc: str):
        """保存HTML格式的测试报告"""
        
        html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>短视频生成平台测试报告</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px 8px 0 0; }}
        .content {{ padding: 30px; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .summary-card {{ background: #f8f9fa; padding: 20px; border-radius: 8px; border-left: 4px solid #007bff; }}
        .test-results {{ margin-top: 30px; }}
        .test-item {{ background: #f8f9fa; margin: 10px 0; padding: 15px; border-radius: 8px; border-left: 4px solid #28a745; }}
        .test-item.failed {{ border-left-color: #dc3545; }}
        .test-item.optional {{ border-left-color: #ffc107; }}
        .health-status {{ background: #e7f3ff; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .timestamp {{ color: #6c757d; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎬 短视频生成平台测试报告</h1>
            <p class="timestamp">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        
        <div class="content">
            <div class="summary">
                <div class="summary-card">
                    <h3>📊 测试概览</h3>
                    <p>总测试套件: {len(self.test_results)}</p>
                    <p>成功: {sum(1 for r in self.test_results.values() if r["success"])}</p>
                    <p>失败: {sum(1 for r in self.test_results.values() if not r["success"])}</p>
                </div>
                
                <div class="summary-card">
                    <h3>⏱️ 执行时间</h3>
                    <p>总耗时: {total_time:.1f} 秒</p>
                    <p>平均每套件: {total_time/len(self.test_results):.1f} 秒</p>
                </div>
                
                <div class="summary-card">
                    <h3>🏥 系统健康</h3>
                    <p>状态: {health_status}</p>
                    <p style="font-size: 0.9em; color: #666;">{health_desc}</p>
                </div>
            </div>
            
            <div class="health-status">
                <h3>💡 健康评估详情</h3>
                <p>{health_desc}</p>
            </div>
            
            <div class="test-results">
                <h3>📋 详细测试结果</h3>
        """
        
        for test_type, result in self.test_results.items():
            status_class = "failed" if not result["success"] else ("optional" if not result.get("required", True) else "")
            status_icon = "✅" if result["success"] else "❌"
            required_text = "必需" if result.get("required", True) else "可选"
            
            html_content += f"""
                <div class="test-item {status_class}">
                    <h4>{status_icon} {result['name']} [{required_text}]</h4>
                    <p>执行时间: {result['execution_time']:.1f} 秒</p>
            """
            
            if not result["success"]:
                if "error" in result:
                    html_content += f"<p style='color: #dc3545;'>错误: {result['error']}</p>"
                if result.get("timeout"):
                    html_content += f"<p style='color: #dc3545;'>原因: 测试超时</p>"
            
            html_content += "</div>"
        
        html_content += """
            </div>
        </div>
    </div>
</body>
</html>
        """
        
        report_file = project_root / "test_results" / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        report_file.parent.mkdir(exist_ok=True)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"        📄 HTML报告已保存: {report_file}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="短视频生成平台测试套件运行器")
    
    parser.add_argument(
        "--tests", 
        nargs="+",
        choices=["e2e", "integration", "ai_services", "performance", "ux"],
        help="指定要运行的测试类型"
    )
    
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="并行运行测试（可能会影响某些测试的准确性）"
    )
    
    parser.add_argument(
        "--mock",
        action="store_true", 
        help="使用模拟模式运行测试（不调用真实AI服务）"
    )
    
    parser.add_argument(
        "--quick",
        action="store_true",
        help="快速模式（跳过长时间运行的测试）"
    )
    
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有可用的测试套件"
    )
    
    args = parser.parse_args()
    
    runner = TestSuiteRunner()
    
    if args.list:
        print("可用的测试套件:")
        for test_type, suite in runner.test_suites.items():
            required_text = "[必需]" if suite["required"] else "[可选]"
            print(f"  {test_type}: {suite['name']} {required_text}")
        return
    
    # 运行测试
    success = runner.run_all_tests(
        test_types=args.tests,
        parallel=args.parallel,
        mock_mode=args.mock,
        quick_mode=args.quick
    )
    
    # 退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()