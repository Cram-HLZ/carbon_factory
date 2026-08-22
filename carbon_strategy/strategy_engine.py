"""
strategy_engine —— 降碳方案引擎

核心类：CarbonStrategyEngine
    根据溯源结果生成三类降碳方案：
        1. equipment_maintenance  设备运维方案
        2. production_scheduling  生产排班方案
        3. process_optimization   工艺优化方案

【多目标优化】
    目标：max(碳减排) + max(成本节约) - min(投资) - min(产量影响)
    约束：产量 ≥ 计划产量、温度 ≤ 安全阈值、人员配置满足
    实现：简单加权评分法排序，竞赛演示够用，不需要复杂求解器

【方案生成方式】
    本阶段用规则引擎 + 方案模板（不依赖强化学习），
    根据 equipment_type 匹配对应模板，填入溯源结果中的具体数值。

后端同学：POST /api/v1/strategy/generate 调用本类的 generate_strategies。
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from config.settings import (
    EQUIPMENT_LIST,
    EQUIPMENT_TYPES,
    WORKSHOPS,
)
from carbon_strategy.equipment_models import estimate_energy_savings


class CarbonStrategyEngine:
    """降碳方案生成器"""

    # 三类方案与目标根因关键词的映射（用于决定优先推荐哪类方案）
    STRATEGY_TYPE_BY_KEYWORD = {
        '温控': 'equipment_maintenance',
        '老化': 'equipment_maintenance',
        '保温': 'equipment_maintenance',
        '振动': 'equipment_maintenance',
        '充电倍率': 'production_scheduling',
        '排班': 'production_scheduling',
        '低负载': 'process_optimization',
        '工艺': 'process_optimization',
        '空载': 'process_optimization',
    }

    # 三类方案的优先级权重（用于排序）
    PRIORITY_WEIGHTS = {
        'high': 3,
        'medium': 2,
        'low': 1,
    }

    def generate_strategies(
        self,
        equipment_id: str,
        analysis_result: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        生成全部三类降碳方案。

        Parameters
        ----------
        equipment_id     : 设备 ID
        analysis_result  : TraceabilityAnalyzer.generate_trace_report 的输出
                          （不传则用默认模板）

        Returns
        -------
        list[dict]，三类方案（运维/排班/工艺）
        """
        info = EQUIPMENT_LIST.get(equipment_id, {})
        eq_type = info.get('equipment_type', 'unknown')
        analysis = analysis_result or {}
        root_causes = analysis.get('root_causes', [])
        top_cause = root_causes[0]['cause'] if root_causes else ''

        strategies = [
            self.equipment_maintenance_strategy(equipment_id, analysis),
            self.production_scheduling_strategy(info.get('workshop_id'), analysis),
            self.process_optimization_strategy(equipment_id, analysis),
        ]
        # 排掉 None（某些设备类型可能没有合适方案）
        strategies = [s for s in strategies if s]
        return self.rank_strategies(strategies, top_cause=top_cause)

    # ============================================================
    # ① 设备运维方案
    # ============================================================
    def equipment_maintenance_strategy(
        self,
        equipment_id: str,
        analysis: Dict,
    ) -> Dict:
        """
        生成设备运维方案。

        针对：烘烤炉温控/化成柜效率/空压机群控/风机变频等
        """
        info = EQUIPMENT_LIST.get(equipment_id, {})
        eq_type = info.get('equipment_type', 'unknown')
        type_info = EQUIPMENT_TYPES.get(eq_type, {})
        workshop_id = info.get('workshop_id')
        rated_power = type_info.get('rated_power', 0)

        # 按 equipment_type 选择对应模板
        template = self._maintenance_templates().get(eq_type)
        if template is None:
            # 兜底：通用设备维护模板
            template = {
                'title': f'{type_info.get("name", equipment_id)} 通用维护建议',
                'actions': [
                    '定期清洁散热/过滤部件',
                    '检查电机轴承润滑，必要时更换',
                    '校准关键传感器（电压/电流/温度）',
                ],
                'estimated_energy_saving': '5%',
                'estimated_carbon_reduction': f'{rated_power * 0.05 * 24 * 0.5810:.1f} kgCO2/天',
                'investment': '¥1,000（常规维护）',
                'priority': 'medium',
            }

        # 注入设备运行时间信息（用于"已运行 XX 小时"等表述）
        actions = [a.format(rated_power=rated_power) if '{rated_power}' in a else a
                   for a in template['actions']]
        # 在 actions 中追加溯源根因的具体描述
        if analysis.get('root_causes'):
            actions.append(
                f"溯源根因：{analysis['root_causes'][0]['cause']} - "
                f"{analysis['root_causes'][0]['detail']}"
            )

        return {
            'strategy_type': 'equipment_maintenance',
            'title': template['title'],
            'target_equipment': equipment_id,
            'target_equipment_name': info.get('name', equipment_id),
            'workshop_id': workshop_id,
            'equipment_type': eq_type,
            'actions': actions,
            'estimated_energy_saving': template['estimated_energy_saving'],
            'estimated_carbon_reduction': template['estimated_carbon_reduction'],
            'estimated_cost_saving': self._calc_cost_saving(rated_power, template['estimated_energy_saving']),
            'investment': template['investment'],
            'payback_period': self._calc_payback(template['investment'], self._calc_cost_saving(rated_power, template['estimated_energy_saving'])),
            'priority': template['priority'],
        }

    # ============================================================
    # ② 生产排班方案
    # ============================================================
    def production_scheduling_strategy(
        self,
        workshop_id: Optional[str],
        analysis: Dict,
    ) -> Dict:
        """
        生成生产排班方案。

        主要针对化成车间 WS-02（16 台化成柜 24h 运行）。
        其它车间默认输出峰谷错峰建议。
        """
        workshop_info = WORKSHOPS.get(workshop_id, {})
        workshop_name = workshop_info.get('name', '未指定车间')

        if workshop_id == 'WS-02':
            return {
                'strategy_type': 'production_scheduling',
                'title': '化成车间错峰充电排班优化',
                'target_workshop': f'{workshop_id}（{workshop_name}）',
                'equipment_count': workshop_info.get('equipment_count', 16),
                'current_schedule': '全天均匀充电，峰电时段(8:00-22:00)充电占比 65%',
                'recommended_schedule': '大电流充电集中在谷电时段(0:00-8:00)，峰电时段仅小电流涓流补电',
                'actions': [
                    '化成柜恒流充电阶段(0.5C-1C)安排在谷电时段 0:00-8:00',
                    '峰电时段 8:00-22:00 仅进行恒压涓流补电(<0.1C)和静置老化',
                    '化成柜分两批轮换：第一批 0:00-8:00 大电流，第二批 8:00-16:00 小电流',
                    '配合 MES 系统排产，确保化成完成时间满足下工序节拍',
                ],
                'estimated_energy_saving': '0%（总电量不变）',
                'estimated_carbon_reduction': '8.5%（谷电时段电网碳排因子更低）',
                'estimated_cost_saving': '¥18,600/月（峰谷电价差，工业用电峰谷比约 3:1）',
                'investment': '¥0（仅 MES 排产参数调整）',
                'payback_period': '即时',
                'priority': 'high',
                'constraints': '需确保化成工艺时间满足质量要求，大电流充电时段需人员值守',
            }

        # 通用排班方案
        return {
            'strategy_type': 'production_scheduling',
            'title': f'{workshop_name} 峰谷错峰排产建议',
            'target_workshop': f'{workshop_id}（{workshop_name}）' if workshop_id else '全厂',
            'equipment_count': workshop_info.get('equipment_count', 0),
            'current_schedule': '当前生产负载全天均匀分布',
            'recommended_schedule': '高耗能工序（烘烤/化成/铣削）尽量安排在谷电时段 0:00-8:00',
            'actions': [
                '峰电时段 8:00-22:00 减少高耗能设备同时启动数量',
                '夜班（TEAM-C）安排高耗能连续工序',
                '与排产系统联动，自动调整工序时序',
            ],
            'estimated_energy_saving': '0%',
            'estimated_carbon_reduction': '5%（错峰带来的电网因子下降）',
            'estimated_cost_saving': '¥8,000/月（峰谷电价差）',
            'investment': '¥0',
            'payback_period': '即时',
            'priority': 'medium',
            'constraints': '需平衡排产节拍，避免下工序待料',
        }

    # ============================================================
    # ③ 工艺优化方案
    # ============================================================
    def process_optimization_strategy(
        self,
        equipment_id: str,
        analysis: Dict,
    ) -> Dict:
        """
        生成工艺优化方案。

        针对卷绕机启停时序、空压机群控、风机变频等。
        """
        info = EQUIPMENT_LIST.get(equipment_id, {})
        eq_type = info.get('equipment_type', 'unknown')
        type_info = EQUIPMENT_TYPES.get(eq_type, {})
        rated_power = type_info.get('rated_power', 0)

        templates = self._process_templates()
        template = templates.get(eq_type)
        if template is None:
            template = {
                'title': f'{type_info.get("name", equipment_id)} 工艺参数优化',
                'actions': [
                    '根据负载波动调整运行参数，避免空载/低负载运行',
                    '采集 PLC 参数曲线，做回归分析识别可优化空间',
                ],
                'estimated_energy_saving': '8%',
                'estimated_carbon_reduction': f'{rated_power * 0.08 * 24 * 0.5810:.1f} kgCO2/天',
                'investment': '¥0（PLC 参数调整）',
                'priority': 'medium',
            }

        actions = [a.format(rated_power=rated_power) if '{rated_power}' in a else a
                   for a in template['actions']]

        return {
            'strategy_type': 'process_optimization',
            'title': template['title'],
            'target_equipment': equipment_id,
            'target_equipment_name': info.get('name', equipment_id),
            'workshop_id': info.get('workshop_id'),
            'equipment_type': eq_type,
            'actions': actions,
            'estimated_energy_saving': template['estimated_energy_saving'],
            'estimated_carbon_reduction': template['estimated_carbon_reduction'],
            'estimated_cost_saving': self._calc_cost_saving(rated_power, template['estimated_energy_saving']),
            'investment': template['investment'],
            'payback_period': self._calc_payback(template['investment'], self._calc_cost_saving(rated_power, template['estimated_energy_saving'])),
            'priority': template['priority'],
        }

    # ============================================================
    # 节能量估算（外部可用）
    # ============================================================
    def estimate_savings(self, strategy: Dict) -> Dict:
        """
        估算方案预期节能/减碳量/经济效益（独立调用）。

        Returns
        -------
        dict: {energy_saving_pct, carbon_reduction_kg_per_day, cost_saving_per_month, payback_months}
        """
        # 从方案 dict 中提取关键字段
        energy_str = strategy.get('estimated_energy_saving', '0%')
        try:
            energy_pct = float(energy_str.replace('%', '').split('（')[0].split('%')[0]) / 100
        except (ValueError, IndexError):
            energy_pct = 0.0
        carbon_str = strategy.get('estimated_carbon_reduction', '0 kgCO2/天')
        try:
            carbon_kg = float(carbon_str.replace(' kgCO2/天', '').replace('kgCO2/天', '').split()[0])
        except (ValueError, IndexError):
            carbon_kg = 0.0
        cost_str = strategy.get('estimated_cost_saving', '¥0/月')
        try:
            cost_yuan = float(cost_str.replace('¥', '').replace(',', '').split('/')[0])
        except (ValueError, IndexError):
            cost_yuan = 0.0
        invest_str = strategy.get('investment', '¥0')
        try:
            investment_yuan = float(invest_str.replace('¥', '').replace(',', '').split('（')[0].strip())
        except (ValueError, IndexError):
            investment_yuan = 0.0

        payback = (investment_yuan / cost_yuan) if cost_yuan > 0 else 0.0
        return {
            'energy_saving_pct': round(energy_pct, 4),
            'carbon_reduction_kg_per_day': round(carbon_kg, 4),
            'cost_saving_per_month': round(cost_yuan, 2),
            'investment_yuan': round(investment_yuan, 2),
            'payback_months': round(payback, 2),
        }

    # ============================================================
    # 方案排序
    # ============================================================
    def rank_strategies(
        self,
        strategies: List[Dict],
        top_cause: str = '',
    ) -> List[Dict]:
        """
        按投入产出比排序。

        排序规则：
            1. 与根因匹配的方案类型优先级提升
            2. priority 字段（high > medium > low）
            3. 投资回收期越短越靠前
        """
        # 找出根因匹配的方案类型
        matched_type = None
        for keyword, st_type in self.STRATEGY_TYPE_BY_KEYWORD.items():
            if keyword in top_cause:
                matched_type = st_type
                break

        def sort_key(s: Dict):
            type_bonus = 1 if s.get('strategy_type') == matched_type else 0
            priority_score = self.PRIORITY_WEIGHTS.get(s.get('priority', 'medium'), 2)
            # 回收期解析（越短越好）
            pp_str = s.get('payback_period', '即时')
            try:
                if '即时' in pp_str:
                    payback_score = 0
                else:
                    pp = float(pp_str.replace('个月', '').strip())
                    payback_score = pp
            except (ValueError, IndexError):
                payback_score = 999
            # 按匹配度 → 优先级 → 回收期升序
            return (-type_bonus, -priority_score, payback_score)

        return sorted(strategies, key=sort_key)

    # ============================================================
    # 模板库（按设备类型）
    # ============================================================
    def _maintenance_templates(self) -> Dict[str, Dict]:
        """设备运维方案模板"""
        return {
            # 烘烤炉：温控校准 + 保温层维护
            'baking_oven': {
                'title': '电芯烘烤炉温控校准与保温层维护',
                'actions': [
                    '校准温度传感器：实测温度偏离基线，需重新校准 PT100 传感器',
                    '检查炉门密封与保温层：红外热成像检测热泄漏点，更换老化密封条',
                    '优化升温曲线：从线性升温改为阶梯升温（80℃保温10min→120℃），减少升温过冲',
                    '建立定期维护台账：每3个月校准一次温控，每6个月检查保温层',
                ],
                'estimated_energy_saving': '15.2%',
                'estimated_carbon_reduction': '23.8 kgCO2/天',
                'investment': '¥2,000（传感器校准+密封条更换）',
                'payback_period': '0.3个月',
                'priority': 'high',
            },
            # 化成柜：充电曲线优化
            'formation_cabinet': {
                'title': '化成柜充电曲线与能效优化',
                'actions': [
                    '校准电流电压传感器，确保充电倍率反馈准确',
                    '调整化成工艺：避免长时间高倍率充电，推荐 0.5C 恒流为主',
                    '检查充电接触电阻，焦耳热损耗是化成柜主要损耗',
                    '余热回收：化成柜散热通过冷却系统收集，用于车间冬季供暖',
                ],
                'estimated_energy_saving': '8.5%',
                'estimated_carbon_reduction': '12.6 kgCO2/天',
                'investment': '¥3,500（传感器校准+接触件清洁）',
                'payback_period': '0.8个月',
                'priority': 'high',
            },
            # 空压机：群控与泄漏治理
            'compressor': {
                'title': '空压机群控与泄漏治理',
                'actions': [
                    '加装变频改造：当前工频运行，负载率波动大，变频后可节能 20%-30%',
                    '空压机群控：3台空压机联动，根据用气需求自动启停，避免多台同时低负载',
                    '压缩空气泄漏治理：全厂管网泄漏率估算 12%-15%，重点检测快速接头、阀门、软管',
                    '调整加卸载压力：加载0.65MPa→0.60MPa，卸载0.75MPa→0.72MPa，降低压缩比',
                    '余热回收：空压机油温80-90℃，可回收用于车间供暖或烘烤炉预热',
                ],
                'estimated_energy_saving': '25.8%',
                'estimated_carbon_reduction': '85.2 kgCO2/天（3台合计）',
                'investment': '¥45,000（变频器3台+群控系统+泄漏检测）',
                'payback_period': '1.9个月',
                'priority': 'high',
            },
            # 冷却风机：变频改造
            'cooling_fan': {
                'title': '冷却风机变频改造',
                'actions': [
                    '变频改造：当前工频运行，根据实际热负荷调节转速',
                    '功率与风量三次方关系：风量下调20%，功率下降约50%',
                    '联控：与冷水机组/环境温度联动，避免过冷运行',
                    '叶轮动平衡校验，振动异常时及时维护',
                ],
                'estimated_energy_saving': '35.0%',
                'estimated_carbon_reduction': '42.0 kgCO2/天（4台合计）',
                'investment': '¥18,000（变频器4台+联控）',
                'payback_period': '1.5个月',
                'priority': 'high',
            },
            # 冷水机组：出水温度优化
            'chiller': {
                'title': '冷水机组出水温度与 COP 优化',
                'actions': [
                    '提升出水温度：当前7℃可上调至9-10℃，每升1℃ COP 提升 2-3%',
                    '避免过低负荷运行：低负荷时 COP 骤降，建议开启台数控制',
                    '冷凝器清洗：结垢使 COP 下降5%-10%',
                    '冷却塔水温控制：与环境温度联动',
                ],
                'estimated_energy_saving': '12.0%',
                'estimated_carbon_reduction': '38.5 kgCO2/天（2台合计）',
                'investment': '¥8,000（清洗+控制参数调整）',
                'payback_period': '0.6个月',
                'priority': 'medium',
            },
            # 数控铣床：维护 + 待机管理
            'cnc_milling_machine': {
                'title': '数控龙门铣床维护与待机管理',
                'actions': [
                    '主轴轴承润滑：长时间运行后润滑失效导致能耗上升',
                    '减少空载待机：超过 5 分钟不加工自动进入节能模式（主轴降至 30%）',
                    '校准切削参数：避免过高进给率导致额外能耗',
                    '检查导轨润滑与刀具磨损',
                ],
                'estimated_energy_saving': '10.0%',
                'estimated_carbon_reduction': '14.8 kgCO2/天（4台合计）',
                'investment': '¥1,500（润滑+维护）',
                'payback_period': '0.5个月',
                'priority': 'medium',
            },
            # 卷绕机：维护
            'winding_machine': {
                'title': '卷绕机驱动系统维护',
                'actions': [
                    '检查伺服电机轴承润滑',
                    '张力传感器校准：张力反馈偏差会导致功率波动',
                    '主轴减速箱油液更换',
                    '加减速曲线优化：减少启停冲击电流',
                ],
                'estimated_energy_saving': '8.0%',
                'estimated_carbon_reduction': '28.5 kgCO2/天（15台合计）',
                'investment': '¥2,500（15台维护）',
                'payback_period': '0.6个月',
                'priority': 'medium',
            },
            # 检测设备：低耗能，通用维护
            'appearance_inspector': {
                'title': '外观检测机维护',
                'actions': ['清洁光源与镜头', '校准相机参数', '检查传送带'],
                'estimated_energy_saving': '3%',
                'estimated_carbon_reduction': '2.1 kgCO2/天',
                'investment': '¥500',
                'payback_period': '1.2个月',
                'priority': 'low',
            },
            'dimension_inspector': {
                'title': '尺寸检测机维护',
                'actions': ['清洁测量平台', '校准激光测头', '检查气路'],
                'estimated_energy_saving': '3%',
                'estimated_carbon_reduction': '1.1 kgCO2/天',
                'investment': '¥400',
                'payback_period': '1.5个月',
                'priority': 'low',
            },
            'sorting_machine': {
                'title': '分选机维护',
                'actions': ['清洁分选通道', '校准分选参数', '检查气缸'],
                'estimated_energy_saving': '4%',
                'estimated_carbon_reduction': '2.8 kgCO2/天',
                'investment': '¥600',
                'payback_period': '1.0个月',
                'priority': 'low',
            },
            # 输送线
            'conveyor_line': {
                'title': '输送流水线维护',
                'actions': ['检查电机润滑', '调整传送带张力', '检查导轨'],
                'estimated_energy_saving': '5%',
                'estimated_carbon_reduction': '1.2 kgCO2/天',
                'investment': '¥800',
                'payback_period': '2.0个月',
                'priority': 'low',
            },
            # AGV
            'agv': {
                'title': 'AGV 充电策略优化',
                'actions': ['在低电量时集中充电', '使用快充模式减少充电时长', '检查电池健康度'],
                'estimated_energy_saving': '6%',
                'estimated_carbon_reduction': '0.5 kgCO2/天',
                'investment': '¥0',
                'payback_period': '即时',
                'priority': 'low',
            },
        }

    def _process_templates(self) -> Dict[str, Dict]:
        """工艺优化方案模板"""
        return {
            'winding_machine': {
                'title': '卷绕机启停时序与张力参数优化',
                'actions': [
                    '优化启停时序：换卷停机时主轴降至待机转速(30%)而非全停，减少启动冲击电流',
                    '15台卷绕机错峰启动：每台间隔30秒启动，避免同时启动造成车间电网峰值',
                    '张力参数优化：当前平均张力12N，根据极片材质优化为分段张力(起步8N→稳态10N→收尾12N)',
                    '卷绕速度优化：从恒定速度改为变速卷绕(内层慢→中层快→外层慢)，减少惯性能耗',
                    '待机模式：换卷超过2分钟自动进入节能模式(加热辊降温至保温温度)',
                ],
                'estimated_energy_saving': '12.6%',
                'estimated_carbon_reduction': '41.5 kgCO2/天（15台合计）',
                'investment': '¥0（PLC程序参数调整）',
                'payback_period': '即时',
                'priority': 'medium',
            },
            'compressor': {
                'title': '空压机群控与变频工艺优化',
                'actions': [
                    '群控策略：根据车间用气需求自动调度 3 台空压机启停',
                    '变频参数：负载率维持在 60%-80% 高效区间',
                    '加卸载压力区间收窄，减少空载能耗',
                    '配合管网压力反馈做闭环控制',
                ],
                'estimated_energy_saving': '22.0%',
                'estimated_carbon_reduction': '72.5 kgCO2/天（3台合计）',
                'investment': '¥0（控制参数调整）',
                'payback_period': '即时',
                'priority': 'high',
            },
            'cooling_fan': {
                'title': '冷却风机变频与风量联控',
                'actions': [
                    '根据环境温度/车间热负荷动态调节风量',
                    '风机相似定律：风量下调20%，功率下降50%',
                    '4 台风机联控，避免单台过载',
                ],
                'estimated_energy_saving': '30.0%',
                'estimated_carbon_reduction': '36.0 kgCO2/天（4台合计）',
                'investment': '¥0',
                'payback_period': '即时',
                'priority': 'high',
            },
            'chiller': {
                'title': '冷水机组出水温度与台数联控',
                'actions': [
                    '出水温度从 7℃ 提升至 9℃（COP 提升 4%-6%）',
                    '低负荷时单台运行，高负荷时双台并联',
                    '冷却塔水温与环境联动',
                ],
                'estimated_energy_saving': '10.0%',
                'estimated_carbon_reduction': '32.1 kgCO2/天（2台合计）',
                'investment': '¥0',
                'payback_period': '即时',
                'priority': 'medium',
            },
            'cnc_milling_machine': {
                'title': '数控铣床切削参数与待机管理优化',
                'actions': [
                    '主轴转速、进给率、切削深度联动优化',
                    '空载 > 5min 自动进入待机模式',
                    '减少换刀等待时间',
                ],
                'estimated_energy_saving': '12.0%',
                'estimated_carbon_reduction': '17.8 kgCO2/天（4台合计）',
                'investment': '¥0',
                'payback_period': '即时',
                'priority': 'medium',
            },
            'formation_cabinet': {
                'title': '化成柜充电工艺优化',
                'actions': [
                    '恒流阶段用 0.5C 而非 1C，能效从 88% 提升到 92%',
                    'SOC 在 20%-80% 区间采用大电流，<20% 或 >80% 降为涓流',
                    '化成结束静置时间根据 SOC 自动调整',
                ],
                'estimated_energy_saving': '8.0%',
                'estimated_carbon_reduction': '11.9 kgCO2/天',
                'investment': '¥0',
                'payback_period': '即时',
                'priority': 'medium',
            },
            'baking_oven': {
                'title': '烘烤炉升温曲线与保温优化',
                'actions': [
                    '升温曲线从线性改为阶梯（80℃保温10min→120℃保温20min）',
                    '保温阶段仅补偿热损失，关闭辅助加热',
                    '降温阶段利用余热预热下一批次',
                ],
                'estimated_energy_saving': '14.0%',
                'estimated_carbon_reduction': '21.9 kgCO2/天',
                'investment': '¥0',
                'payback_period': '即时',
                'priority': 'high',
            },
            'agv': {
                'title': 'AGV 充电调度优化',
                'actions': [
                    '调度集中到谷电时段充电',
                    '低于 30% SOC 时启动快充',
                ],
                'estimated_energy_saving': '5.0%',
                'estimated_carbon_reduction': '0.4 kgCO2/天',
                'investment': '¥0',
                'payback_period': '即时',
                'priority': 'low',
            },
        }

    # ============================================================
    # 经济性估算
    # ============================================================
    @staticmethod
    def _calc_cost_saving(rated_power: float, energy_saving_str: str) -> str:
        """
        从节能百分比估算月度成本节约。
        假设工业电价 0.7 元/kWh，设备每天运行 16h。
        """
        try:
            pct_str = energy_saving_str.replace('%', '').split('（')[0].strip()
            pct = float(pct_str) / 100
        except (ValueError, IndexError):
            pct = 0.0
        # 月度节约 = 节能比例 × 额定功率 × 16h × 30天 × 0.7元/kWh
        monthly_saving = pct * rated_power * 16 * 30 * 0.7
        return f'¥{monthly_saving:,.0f}/月'

    @staticmethod
    def _calc_payback(investment_str: str, cost_saving_str: str) -> str:
        """从投资额与月度节约估算回收期"""
        try:
            invest = float(investment_str.replace('¥', '').replace(',', '').split('（')[0].strip())
            saving = float(cost_saving_str.replace('¥', '').replace(',', '').split('/')[0].strip())
            if saving <= 0:
                return '即时' if invest == 0 else '需评估'
            if invest == 0:
                return '即时'
            months = invest / saving
            return f'{months:.1f}个月' if months >= 0.1 else '即时'
        except (ValueError, IndexError):
            return '需评估'
