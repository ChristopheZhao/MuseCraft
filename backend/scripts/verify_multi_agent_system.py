#!/usr/bin/env python3
"""
多Agent系统架构验证脚本
验证所有Agent是否正确实现批量ReAct模式
"""

import asyncio
import inspect
import sys
import os
from pathlib import Path
from typing import Dict, List, Any

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from app.agents.base import BaseAgent
    from app.agents.react_agent import ReActAgent
    from app.agents.image_generator import ImageGeneratorAgent
    from app.agents.video_generator import VideoGeneratorAgent  
    from app.agents.script_writer import ScriptWriterAgent
    from app.agents.concept_planner import ConceptPlannerAgent
    from app.agents.video_composer import VideoComposerAgent
    from app.agents.quality_checker import QualityCheckerAgent
    from app.models import AgentType
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("请确保在正确的项目目录下运行此脚本")
    sys.exit(1)


class AgentArchitectureValidator:
    """Agent架构验证器"""
    
    def __init__(self):
        self.results = {
            "agents_tested": 0,
            "react_compliant": [],
            "needs_fixing": [],
            "detailed_analysis": {}
        }
    
    async def validate_all_agents(self) -> Dict[str, Any]:
        """验证所有Agent的架构合规性"""
        
        agents_to_test = [
            ("ImageGenerator", ImageGeneratorAgent),
            ("VideoGenerator", VideoGeneratorAgent),
            ("ScriptWriter", ScriptWriterAgent),
            ("ConceptPlanner", ConceptPlannerAgent),
            ("VideoComposer", VideoComposerAgent),
            ("QualityChecker", QualityCheckerAgent),
        ]
        
        print("🔍 开始Agent架构验证...\n")
        
        for agent_name, agent_class in agents_to_test:
            print(f"📋 验证 {agent_name}...")
            analysis = await self._analyze_agent_architecture(agent_name, agent_class)
            self.results["detailed_analysis"][agent_name] = analysis
            
            if analysis["is_react_compliant"]:
                self.results["react_compliant"].append(agent_name)
                print(f"  ✅ {agent_name} - ReAct模式合规")
            else:
                self.results["needs_fixing"].append(agent_name)
                print(f"  ❌ {agent_name} - 需要修复")
                for issue in analysis["issues"]:
                    print(f"     - {issue}")
            
            self.results["agents_tested"] += 1
        
        return self.results
    
    async def _analyze_agent_architecture(self, agent_name: str, agent_class) -> Dict[str, Any]:
        """分析单个Agent的架构"""
        
        analysis = {
            "agent_name": agent_name,
            "base_class": None,
            "is_react_compliant": False,
            "has_batch_methods": False,
            "has_hardcoded_loops": False,
            "react_methods_present": [],
            "missing_react_methods": [],
            "loop_violations": [],
            "issues": []
        }
        
        try:
            # 检查基类
            base_classes = [cls.__name__ for cls in agent_class.__mro__[1:]]
            analysis["base_class"] = base_classes[0] if base_classes else "Unknown"
            
            # 检查是否继承自ReActAgent
            is_react_agent = any(cls.__name__ == "ReActAgent" for cls in agent_class.__mro__)
            
            # 获取所有方法
            methods = [method for method in dir(agent_class) if callable(getattr(agent_class, method))]
            
            # 检查ReAct必需方法
            required_react_methods = [
                "_observe_current_state",
                "_think_and_plan", 
                "_execute_action",
                "_reflect_on_results"
            ]
            
            for method in required_react_methods:
                if method in methods:
                    analysis["react_methods_present"].append(method)
                else:
                    analysis["missing_react_methods"].append(method)
            
            # 检查批量处理方法
            batch_methods = [method for method in methods if "batch" in method.lower()]
            analysis["has_batch_methods"] = len(batch_methods) > 0
            
            # 检查源代码中的硬编码循环
            loop_violations = await self._check_hardcoded_loops(agent_class)
            analysis["has_hardcoded_loops"] = len(loop_violations) > 0
            analysis["loop_violations"] = loop_violations
            
            # 综合判断
            if is_react_agent:
                if len(analysis["missing_react_methods"]) == 0:
                    if not analysis["has_hardcoded_loops"]:
                        analysis["is_react_compliant"] = True
                    else:
                        analysis["issues"].append("包含硬编码循环处理")
                else:
                    analysis["issues"].append(f"缺少ReAct方法: {', '.join(analysis['missing_react_methods'])}")
            else:
                analysis["issues"].append(f"未继承ReActAgent (当前基类: {analysis['base_class']})")
            
            if not analysis["has_batch_methods"]:
                analysis["issues"].append("缺少批量处理方法")
            
        except Exception as e:
            analysis["issues"].append(f"分析失败: {str(e)}")
        
        return analysis
    
    async def _check_hardcoded_loops(self, agent_class) -> List[str]:
        """检查源代码中的硬编码循环"""
        violations = []
        
        try:
            # 获取源代码
            source_file = inspect.getfile(agent_class)
            with open(source_file, 'r', encoding='utf-8') as f:
                source_code = f.read()
            
            lines = source_code.split('\n')
            
            # 检查for循环和while循环
            for line_num, line in enumerate(lines, 1):
                stripped_line = line.strip()
                
                # 跳过注释行
                if stripped_line.startswith('#'):
                    continue
                
                # 检查硬编码决策循环（非数据处理循环）
                if 'for ' in stripped_line and 'scene' in stripped_line.lower():
                    # 区分数据处理循环和硬编码决策循环
                    if any(keyword in stripped_line.lower() for keyword in [
                        'should_process', 'process_scene', 'generate_scene', 
                        'if scene', 'await.*scene', 'scene.duration', 'scene.status'
                    ]):
                        violations.append(f"第{line_num}行: 硬编码场景处理循环 - {stripped_line}")
                elif 'while ' in stripped_line and 'iteration' not in stripped_line.lower():
                    violations.append(f"第{line_num}行: while循环 - {stripped_line}")
                    
        except Exception as e:
            violations.append(f"源代码检查失败: {str(e)}")
        
        return violations
    
    def print_summary_report(self):
        """打印验证总结报告"""
        
        print("\n" + "="*80)
        print("🎯 多Agent系统架构验证报告")
        print("="*80)
        
        total_agents = self.results["agents_tested"]
        compliant_count = len(self.results["react_compliant"])
        needs_fixing_count = len(self.results["needs_fixing"])
        
        print(f"\n📊 总体统计:")
        print(f"   • 总测试Agent数: {total_agents}")
        print(f"   • ✅ ReAct合规Agent: {compliant_count}")
        print(f"   • ❌ 需要修复Agent: {needs_fixing_count}")
        print(f"   • 🎯 合规率: {(compliant_count/total_agents)*100:.1f}%")
        
        if self.results["react_compliant"]:
            print(f"\n✅ 已修复的Agent:")
            for agent in self.results["react_compliant"]:
                print(f"   • {agent}")
        
        if self.results["needs_fixing"]:
            print(f"\n❌ 仍需修复的Agent:")
            for agent in self.results["needs_fixing"]:
                analysis = self.results["detailed_analysis"][agent]
                print(f"   • {agent}:")
                for issue in analysis["issues"]:
                    print(f"     - {issue}")
        
        print(f"\n🎯 架构修复目标:")
        print(f"   1. 所有Agent继承ReActAgent")
        print(f"   2. 实现完整ReAct方法集")
        print(f"   3. 移除硬编码循环处理")
        print(f"   4. 实现批量处理模式")
        print(f"   5. 任务完成度驱动迭代")
        
        print("\n" + "="*80)
        
        # 返回是否全部合规
        return needs_fixing_count == 0


async def main():
    """主函数"""
    
    print("🚀 MuseCraft 多Agent系统架构验证")
    print("   验证所有Agent是否正确实现批量ReAct模式\n")
    
    validator = AgentArchitectureValidator()
    
    try:
        # 执行验证
        results = await validator.validate_all_agents()
        
        # 打印报告
        all_compliant = validator.print_summary_report()
        
        # 返回适当的退出码
        if all_compliant:
            print("🎉 所有Agent已正确实现ReAct架构！")
            sys.exit(0)
        else:
            print("⚠️  部分Agent仍需架构修复")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ 验证过程失败: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())