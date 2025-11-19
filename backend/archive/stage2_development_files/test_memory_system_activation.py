#!/usr/bin/env python3
"""
测试记忆系统激活和Agent间记忆共享
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

def test_memory_system_activation():
    """测试记忆系统激活效果"""
    
    print("🧠 测试记忆系统激活...")
    
    try:
        # 测试各个Agent的记忆系统激活
        agents_to_test = [
            ("ConceptPlannerAgent", "app.agents.concept_planner"),
            ("ScriptWriterAgent", "app.agents.script_writer"),
            ("ImageGeneratorAgent", "app.agents.image_generator"),
            ("QualityCheckerAgent", "app.agents.quality_checker"),
            ("VideoGeneratorAgent", "app.agents.video_generator")
        ]
        
        activated_agents = []
        
        for agent_name, module_path in agents_to_test:
            try:
                # 动态导入并实例化Agent
                module = __import__(module_path, fromlist=[agent_name])
                agent_class = getattr(module, agent_name)
                agent = agent_class()
                
                # 检查记忆系统状态
                memory_manager_status = "activated" if agent.memory_manager is not None else "disabled"
                memory_service_status = "activated" if hasattr(agent, 'memory_service') and agent.memory_service is not None else "disabled"
                
                # 检查MAS记忆共享方法
                has_creative_guidance = hasattr(agent, 'store_creative_guidance') and hasattr(agent, 'retrieve_creative_guidance')
                has_scene_references = hasattr(agent, 'store_scene_references') and hasattr(agent, 'retrieve_scene_references')
                
                if memory_manager_status == "activated" and memory_service_status == "activated":
                    print(f"✅ {agent_name}: memory_manager={memory_manager_status}, memory_service={memory_service_status}")
                    if has_creative_guidance and has_scene_references:
                        print(f"   🚀 MAS记忆共享方法已激活")
                        activated_agents.append(agent_name)
                    else:
                        print(f"   ⚠️ 缺少MAS记忆共享方法")
                else:
                    print(f"❌ {agent_name}: memory_manager={memory_manager_status}, memory_service={memory_service_status}")
                    
            except Exception as e:
                print(f"❌ {agent_name}: 实例化失败 - {e}")
        
        print(f"\n📊 记忆系统激活统计:")
        print(f"   成功激活: {len(activated_agents)}/{len(agents_to_test)}个Agent")
        print(f"   激活列表: {activated_agents}")
        
        # 测试GlobalMemoryService功能
        print(f"\n🔧 测试GlobalMemoryService...")
        from app.services.global_memory_service import global_memory_service
        
        # 检查单例
        from app.services.global_memory_service import GlobalMemoryService
        service2 = GlobalMemoryService()
        is_singleton = global_memory_service is service2
        print(f"✅ 单例模式: {'正确' if is_singleton else '错误'}")
        
        # 检查MemoryManager
        has_memory_manager = hasattr(global_memory_service, 'memory_manager') and global_memory_service.memory_manager is not None
        print(f"✅ MemoryManager: {'已初始化' if has_memory_manager else '未初始化'}")
        
        # 测试基础记忆操作
        if has_memory_manager:
            print(f"🧪 测试基础记忆操作...")
            
            # 测试存储记忆
            import asyncio
            from app.agents.memory.long_term.stores import MemoryType, MemoryImportance
            
            async def test_basic_memory():
                try:
                    # 存储测试记忆
                    memory_id = await global_memory_service.memory_manager.store_memory(
                        content={"test": "Phase 1.2 memory activation"},
                        memory_type=MemoryType.SHORT_TERM,
                        importance=MemoryImportance.MEDIUM,
                        tags=["test", "activation"],
                        agent_id="test_agent"
                    )
                    
                    # 检索记忆
                    memories = await global_memory_service.memory_manager.search_memories(
                        tags=["test"],
                        agent_id="test_agent",
                        limit=1
                    )
                    
                    if memories and len(memories) > 0:
                        print(f"   ✅ 记忆存储/检索测试通过")
                        return True
                    else:
                        print(f"   ❌ 记忆检索失败")
                        return False
                        
                except Exception as e:
                    print(f"   ❌ 记忆操作失败: {e}")
                    return False
            
            # 运行异步测试
            try:
                loop = asyncio.get_event_loop()
                memory_test_passed = loop.run_until_complete(test_basic_memory())
            except RuntimeError:
                # 如果没有事件循环，创建一个新的
                memory_test_passed = asyncio.run(test_basic_memory())
        else:
            memory_test_passed = False
        
        # 最终结果
        if len(activated_agents) == len(agents_to_test) and memory_test_passed:
            print(f"\n🎉 记忆系统完全激活成功!")
            print(f"✨ 所有Agent都具备MAS记忆共享能力")
            print(f"🚀 Phase 1.2 - 记忆系统激活完成")
            return True
        else:
            print(f"\n⚠️ 记忆系统激活不完整:")
            print(f"   Agent激活: {len(activated_agents)}/{len(agents_to_test)}")
            print(f"   记忆测试: {'通过' if memory_test_passed else '失败'}")
            return False
            
    except Exception as e:
        print(f"❌ 记忆系统测试失败: {e}")
        return False

if __name__ == "__main__":
    success = test_memory_system_activation()
    sys.exit(0 if success else 1)
