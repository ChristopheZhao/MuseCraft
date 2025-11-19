#!/usr/bin/env python3
"""
简化的多智能体系统验证脚本
直接检查文件结构和关键组件的存在
"""

import os
import sys
from pathlib import Path
import importlib.util
import ast
import json

# 项目根目录
project_root = Path(__file__).parent.parent
backend_root = project_root / "backend"

class MultiAgentSystemVerifier:
    """多智能体系统验证器"""
    
    def __init__(self):
        self.results = {}
        
    def check_file_exists(self, file_path: Path) -> bool:
        """检查文件是否存在"""
        return file_path.exists() and file_path.is_file()
    
    def check_class_in_file(self, file_path: Path, class_name: str) -> bool:
        """检查文件中是否包含指定类"""
        if not self.check_file_exists(file_path):
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                tree = ast.parse(content)
                
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    return True
            return False
        except:
            return False
    
    def check_method_in_class(self, file_path: Path, class_name: str, method_name: str) -> bool:
        """检查类中是否包含指定方法（支持异步方法）"""
        if not self.check_file_exists(file_path):
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    for item in node.body:
                        # 同时检查同步方法 (FunctionDef) 和异步方法 (AsyncFunctionDef)
                        if ((isinstance(item, ast.FunctionDef) or isinstance(item, ast.AsyncFunctionDef)) 
                            and item.name == method_name):
                            return True
            return False
        except Exception as e:
            print(f"Error checking {file_path}: {e}")
            return False
    
    def verify_agent_architecture(self) -> dict:
        """验证智能体架构"""
        print("🔍 验证智能体架构...")
        
        # 检查基础智能体类
        base_agent_path = backend_root / "app/agents/base.py"
        base_agent_exists = self.check_class_in_file(base_agent_path, "BaseAgent")
        
        # 检查所有专业智能体
        agents = {
            "OrchestratorAgent": "orchestrator.py",
            "ReActOrchestratorAgent": "react_orchestrator.py", 
            "ConceptPlannerAgent": "concept_planner.py",
            "ScriptWriterAgent": "script_writer.py",
            "ImageGeneratorAgent": "image_generator.py",
            "VideoGeneratorAgent": "video_generator.py",
            "VideoComposerAgent": "video_composer.py",
            "QualityCheckerAgent": "quality_checker.py"
        }
        
        agent_status = {}
        for agent_class, filename in agents.items():
            agent_path = backend_root / f"app/agents/{filename}"
            agent_status[agent_class] = {
                "file_exists": self.check_file_exists(agent_path),
                "class_exists": self.check_class_in_file(agent_path, agent_class),
                "has_execute_impl": self.check_method_in_class(agent_path, agent_class, "_execute_impl")
            }
        
        return {
            "base_agent_exists": base_agent_exists,
            "agent_status": agent_status,
            "total_agents": len(agents),
            "valid_agents": sum(1 for status in agent_status.values() 
                               if all(status.values()))
        }
    
    def verify_orchestration_modes(self) -> dict:
        """验证编排模式"""
        print("🔍 验证编排模式...")
        
        # 检查Pipeline模式
        orchestrator_path = backend_root / "app/agents/orchestrator.py"
        pipeline_features = {
            "file_exists": self.check_file_exists(orchestrator_path),
            "class_exists": self.check_class_in_file(orchestrator_path, "OrchestratorAgent"),
            "has_workflow_order": "workflow_order" in open(orchestrator_path).read() if orchestrator_path.exists() else False
        }
        
        # 检查ReAct模式
        react_path = backend_root / "app/agents/react_orchestrator.py"
        react_features = {
            "file_exists": self.check_file_exists(react_path),
            "class_exists": self.check_class_in_file(react_path, "ReActOrchestratorAgent"),
            "has_observe": self.check_method_in_class(react_path, "ReActOrchestratorAgent", "_observe_current_state"),
            "has_think": self.check_method_in_class(react_path, "ReActOrchestratorAgent", "_think_and_reason"),
            "has_plan": self.check_method_in_class(react_path, "ReActOrchestratorAgent", "_plan_next_action"),
            "has_act": self.check_method_in_class(react_path, "ReActOrchestratorAgent", "_execute_action"),
            "has_reflect": self.check_method_in_class(react_path, "ReActOrchestratorAgent", "_reflect_on_results")
        }
        
        return {
            "pipeline_mode": pipeline_features,
            "react_mode": react_features,
            "both_modes_available": all(pipeline_features.values()) and all(react_features.values())
        }
    
    def verify_tool_system(self) -> dict:
        """验证工具系统"""
        print("🔍 验证工具系统...")
        
        tools_root = backend_root / "app/agents/tools"
        
        # 检查基础工具类
        base_tool_path = tools_root / "base_tool.py"
        base_tool_features = {
            "file_exists": self.check_file_exists(base_tool_path),
            "has_base_tool": self.check_class_in_file(base_tool_path, "BaseTool"),
            "has_async_tool": self.check_class_in_file(base_tool_path, "AsyncTool"),
            "has_tool_input": self.check_class_in_file(base_tool_path, "ToolInput")
        }
        
        # 检查工具注册表
        registry_path = tools_root / "tool_registry.py"
        registry_features = {
            "file_exists": self.check_file_exists(registry_path),
            "has_registry": self.check_class_in_file(registry_path, "ToolRegistry")
        }
        
        # 检查具体工具实现
        tool_categories = {
            "ai_services": ["openai_client.py", "kimi_client.py", "zhipu_client.py", "image_generation_client.py"],
            "video_processing": ["ffmpeg_tool.py"],
            "storage": ["file_storage_tool.py"],
            "video_composition": ["video_composer_tool.py"]
        }
        
        tool_status = {}
        for category, tool_files in tool_categories.items():
            category_path = tools_root / category
            tool_status[category] = {
                "directory_exists": category_path.exists(),
                "tools": {}
            }
            
            for tool_file in tool_files:
                tool_path = category_path / tool_file
                tool_name = tool_file.replace(".py", "")
                tool_status[category]["tools"][tool_name] = {
                    "file_exists": self.check_file_exists(tool_path)
                }
        
        return {
            "base_tool_features": base_tool_features,
            "registry_features": registry_features,
            "tool_categories": tool_status,
            "total_categories": len(tool_categories)
        }
    
    def verify_memory_management(self) -> dict:
        """验证记忆管理系统"""
        print("🔍 验证记忆管理系统...")
        
        memory_root = backend_root / "app/agents/memory"
        
        # 检查基础记忆类
        base_memory_path = memory_root / "long_term" / "stores" / "base.py"
        base_memory_features = {
            "file_exists": self.check_file_exists(base_memory_path),
            "has_memory_item": self.check_class_in_file(base_memory_path, "MemoryItem"),
            "has_memory_query": self.check_class_in_file(base_memory_path, "MemoryQuery"),
            "has_base_memory_store": self.check_class_in_file(base_memory_path, "BaseMemoryStore")
        }
        
        # 检查记忆管理器
        memory_manager_path = memory_root / "long_term" / "manager" / "memory_manager.py"
        manager_features = {
            "file_exists": self.check_file_exists(memory_manager_path),
            "has_manager": self.check_class_in_file(memory_manager_path, "MemoryManager"),
            "has_store_method": self.check_method_in_class(memory_manager_path, "MemoryManager", "store_memory"),
            "has_retrieve_method": self.check_method_in_class(memory_manager_path, "MemoryManager", "retrieve_memory"),
            "has_search_method": self.check_method_in_class(memory_manager_path, "MemoryManager", "search_memories")
        }
        
        return {
            "base_memory_features": base_memory_features,
            "manager_features": manager_features,
            "memory_system_complete": all(base_memory_features.values()) and all(manager_features.values())
        }
    
    def verify_prompt_templates(self) -> dict:
        """验证提示词模板系统"""
        print("🔍 验证提示词模板系统...")
        
        prompts_root = backend_root / "app/agents/prompts"
        
        # 检查模板管理器
        template_manager_path = prompts_root / "template_manager.py"
        template_features = {
            "file_exists": self.check_file_exists(template_manager_path),
            "has_manager": self.check_class_in_file(template_manager_path, "PromptTemplateManager")
        }
        
        # 检查模板文件（修正路径）
        templates_dir = prompts_root / "templates"
        template_files = [
            "concept_planner/concept_planner.yaml",
            "script_writer/script_writer.yaml", 
            "quality_checker/quality_checker.yaml",
            "orchestrator/react_orchestrator.yaml"
        ]
        
        template_status = {}
        for template_file in template_files:
            template_path = templates_dir / template_file  
            template_status[template_file] = {
                "file_exists": self.check_file_exists(template_path)
            }
        
        return {
            "template_features": template_features,
            "template_status": template_status,
            "templates_directory_exists": templates_dir.exists()
        }
    
    def verify_models_and_database(self) -> dict:
        """验证数据模型和数据库集成"""
        print("🔍 验证数据模型...")
        
        models_root = backend_root / "app/models"
        
        model_files = {
            "base.py": "BaseModel",
            "task.py": "Task", 
            "agent.py": "AgentExecution",
            "scene.py": "Scene",
            "resource.py": "Resource"
        }
        
        model_status = {}
        for model_file, model_class in model_files.items():
            model_path = models_root / model_file
            model_status[model_file] = {
                "file_exists": self.check_file_exists(model_path),
                "has_class": self.check_class_in_file(model_path, model_class)
            }
        
        return {
            "model_status": model_status,
            "models_complete": all(
                status["file_exists"] and status["has_class"] 
                for status in model_status.values()
            )
        }
    
    def verify_integration_points(self) -> dict:
        """验证系统集成点"""
        print("🔍 验证系统集成点...")
        
        # 检查BaseAgent中的集成
        base_agent_path = backend_root / "app/agents/base.py"
        
        integration_features = {}
        if self.check_file_exists(base_agent_path):
            content = open(base_agent_path).read()
            integration_features = {
                "has_tool_registry": "tool_registry" in content,
                "has_memory_manager": "memory_manager" in content,
                "has_template_manager": "template_manager" in content,
                "has_use_tool_method": "async def use_tool" in content,
                "has_store_memory_method": "async def store_memory" in content,
                "has_render_prompt_method": "async def render_prompt" in content
            }
        
        return {
            "base_agent_integration": integration_features,
            "integration_complete": all(integration_features.values()) if integration_features else False
        }
    
    def run_all_verifications(self) -> dict:
        """运行所有验证"""
        print("🚀 开始多智能体系统验证\n")
        
        verifications = [
            ("agent_architecture", self.verify_agent_architecture),
            ("orchestration_modes", self.verify_orchestration_modes),
            ("tool_system", self.verify_tool_system),
            ("memory_management", self.verify_memory_management),
            ("prompt_templates", self.verify_prompt_templates),
            ("models_database", self.verify_models_and_database),
            ("integration_points", self.verify_integration_points)
        ]
        
        results = {}
        for name, verify_func in verifications:
            try:
                result = verify_func()
                results[name] = result
                print(f"✅ {name} 验证完成")
            except Exception as e:
                results[name] = {"error": str(e)}
                print(f"❌ {name} 验证失败: {e}")
            print()
        
        return results
    
    def generate_summary_report(self, results: dict) -> str:
        """生成摘要报告"""
        report = ["🎬 多智能体系统验证报告", "=" * 50, ""]
        
        # 智能体架构摘要
        if "agent_architecture" in results:
            arch = results["agent_architecture"]
            if "valid_agents" in arch:
                report.extend([
                    "🤖 智能体架构:",
                    f"   基础智能体: {'✅' if arch.get('base_agent_exists') else '❌'}",
                    f"   专业智能体: {arch.get('valid_agents', 0)}/{arch.get('total_agents', 0)}",
                    ""
                ])
        
        # 编排模式摘要
        if "orchestration_modes" in results:
            modes = results["orchestration_modes"]
            report.extend([
                "🔄 编排模式:",
                f"   Pipeline模式: {'✅' if modes.get('pipeline_mode', {}).get('class_exists') else '❌'}",
                f"   ReAct模式: {'✅' if modes.get('react_mode', {}).get('class_exists') else '❌'}",
                f"   ReAct完整性: {'✅' if all(modes.get('react_mode', {}).values()) else '❌'}",
                ""
            ])
        
        # 工具系统摘要
        if "tool_system" in results:
            tools = results["tool_system"]
            total_categories = tools.get("total_categories", 0)
            available_categories = sum(
                1 for cat_info in tools.get("tool_categories", {}).values()
                if cat_info.get("directory_exists", False)
            )
            report.extend([
                "🛠️ 工具系统:",
                f"   基础工具类: {'✅' if tools.get('base_tool_features', {}).get('has_base_tool') else '❌'}",
                f"   工具注册表: {'✅' if tools.get('registry_features', {}).get('has_registry') else '❌'}",
                f"   工具分类: {available_categories}/{total_categories}",
                ""
            ])
        
        # 记忆管理摘要
        if "memory_management" in results:
            memory = results["memory_management"]
            report.extend([
                "🧠 记忆管理:",
                f"   基础记忆类: {'✅' if memory.get('base_memory_features', {}).get('has_memory_item') else '❌'}",
                f"   记忆管理器: {'✅' if memory.get('manager_features', {}).get('has_manager') else '❌'}",
                f"   系统完整性: {'✅' if memory.get('memory_system_complete') else '❌'}",
                ""
            ])
        
        # 提示词模板摘要
        if "prompt_templates" in results:
            templates = results["prompt_templates"]
            template_count = sum(
                1 for status in templates.get("template_status", {}).values()
                if status.get("file_exists", False)
            )
            total_templates = len(templates.get("template_status", {}))
            
            report.extend([
                "📝 提示词模板:",
                f"   模板管理器: {'✅' if templates.get('template_features', {}).get('has_manager') else '❌'}",
                f"   模板文件: {template_count}/{total_templates}",
                ""
            ])
        
        # 集成点摘要
        if "integration_points" in results:
            integration = results["integration_points"]
            report.extend([
                "🔗 系统集成:",
                f"   工具集成: {'✅' if integration.get('base_agent_integration', {}).get('has_use_tool_method') else '❌'}",
                f"   记忆集成: {'✅' if integration.get('base_agent_integration', {}).get('has_store_memory_method') else '❌'}",
                f"   模板集成: {'✅' if integration.get('base_agent_integration', {}).get('has_render_prompt_method') else '❌'}",
                ""
            ])
        
        # 总体评估
        total_checks = len(results)
        passed_checks = 0
        
        for key, result in results.items():
            if isinstance(result, dict) and "error" not in result:
                # 更准确的检查方式
                check_passed = False
                
                if key == "agent_architecture":
                    check_passed = result.get("valid_agents", 0) == result.get("total_agents", 0)
                elif key == "orchestration_modes":
                    check_passed = result.get("both_modes_available", False)
                elif key == "tool_system":
                    check_passed = (result.get("base_tool_features", {}).get("has_base_tool", False) 
                                  and result.get("registry_features", {}).get("has_registry", False))
                elif key == "memory_management":
                    check_passed = result.get("memory_system_complete", False)
                elif key == "prompt_templates":
                    template_count = sum(1 for status in result.get("template_status", {}).values() 
                                       if status.get("file_exists", False))
                    check_passed = template_count > 0
                elif key == "models_database":
                    check_passed = result.get("models_complete", False)
                elif key == "integration_points":
                    check_passed = result.get("integration_complete", False)
                
                if check_passed:
                    passed_checks += 1
        
        success_rate = (passed_checks / total_checks) * 100 if total_checks > 0 else 0
        
        report.extend([
            "📊 总体评估:",
            f"   验证项目: {total_checks}",
            f"   大致通过率: {success_rate:.1f}%",
            f"   系统状态: {'🎉 基本完整' if success_rate >= 70 else '⚠️ 需要完善'}",
            ""
        ])
        
        return "\n".join(report)

def main():
    """主函数"""
    verifier = MultiAgentSystemVerifier()
    results = verifier.run_all_verifications()
    
    # 生成摘要报告
    summary = verifier.generate_summary_report(results)
    print(summary)
    
    # 保存详细结果
    report_file = project_root / "multi_agent_verification_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"📝 详细结果已保存到: {report_file}")

if __name__ == "__main__":
    main()
