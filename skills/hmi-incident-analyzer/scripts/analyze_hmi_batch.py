#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HMI 事故工单批量分析脚本 v1.0
由 hmi-incident-analyzer skill 调用，支持命令行参数配置

用法:
  python analyze_hmi_batch.py [options]

选项:
  --bitable_url   飞书 Bitable URL（必填，或通过环境变量 HMI_BITABLE_URL）
  --mode          处理模式: auto | driving | parking | all（默认 auto）
  --dry_run       仅预览不写入（默认 false）
  --limit         处理条数上限，0=全量（默认 0）
  --data_file     本地数据文件路径（默认 ~/bitable_raw.json）
  --scene_field   HMI-事故场景字段名（默认 HMI-事故场景）
  --cause_field   HMI-事故原因字段名（默认 HMI-事故原因）
  --text8_field   ADAS系统方案字段名（默认 文本 8）
  --text9_field   文本8关键词字段名（默认 文本 9）
  --text10_field  HMI交互方案字段名（默认 文本 10）
  --text11_field  文本10关键词字段名（默认 文本 11）
  --hmi_field     HMI方案源字段名（默认 HMI方案）
  --func_field    功能分类字段名（默认 功能分类）
  --ticket_field  工单链接字段名（默认 工单链接）
  --driving_cats  行车碰撞功能分类值（逗号分隔，默认 行车碰撞,行车碰撞风险）
  --parking_cat   泊车碰撞功能分类值（默认 泊车碰撞）
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


# ─────────────────────────────────────────────────────────
# 参数解析
# ─────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description='HMI 事故工单批量分析')
    p.add_argument('--bitable_url', default=os.environ.get('HMI_BITABLE_URL', ''))
    p.add_argument('--mode', default='auto', choices=['auto', 'driving', 'parking', 'all'])
    p.add_argument('--dry_run', action='store_true')
    p.add_argument('--limit', type=int, default=0)
    p.add_argument('--data_file', default='')
    # 目标字段
    p.add_argument('--scene_field',  default='HMI-事故场景')
    p.add_argument('--cause_field',  default='HMI-事故原因')
    p.add_argument('--text8_field',  default='文本 8')
    p.add_argument('--text9_field',  default='文本 9')
    p.add_argument('--text10_field', default='文本 10')
    p.add_argument('--text11_field', default='文本 11')
    # 源字段
    p.add_argument('--hmi_field',    default='HMI方案')
    p.add_argument('--func_field',   default='功能分类')
    p.add_argument('--ticket_field', default='工单链接')
    p.add_argument('--remark_field', default='备注')
    p.add_argument('--fault_field',  default='故障分类')
    p.add_argument('--l2_field',     default='二级分类')
    p.add_argument('--l3_field',     default='三级分类')
    p.add_argument('--validate_field', default='如何验证方案有效性')
    # 分类判断
    p.add_argument('--driving_cats', default='行车碰撞,行车碰撞风险')
    p.add_argument('--parking_cat',  default='泊车碰撞')
    return p.parse_args()


# ─────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────
def gs(fields: dict, key: str) -> str:
    """安全获取字段值"""
    v = fields.get(key)
    if v is None:
        return ''
    if isinstance(v, list):
        # 处理 User/Link 类型字段
        parts = []
        for item in v:
            if isinstance(item, dict):
                parts.append(item.get('name', item.get('text', str(item))))
            else:
                parts.append(str(item))
        return '；'.join(parts)
    return str(v).strip()


def parse_bitable_url(url: str):
    """从 Bitable URL 解析 app_token 和 table_id"""
    # wiki URL: /wiki/TOKEN?table=TABLE_ID
    m = re.search(r'/wiki/(\w+).*[?&]table=(\w+)', url)
    if m:
        wiki_token, table_id = m.group(1), m.group(2)
        # wiki token 需要先解析为 bitable app_token（通过 feishu-sync）
        # 这里假设已通过 feishu-sync read_page 获取到 app_token
        return None, table_id  # app_token 从 data_file 获取

    # direct URL: /base/APP_TOKEN?table=TABLE_ID
    m = re.search(r'/base/(\w+).*[?&]table=(\w+)', url)
    if m:
        return m.group(1), m.group(2)

    return None, None


def get_token() -> str:
    """从 feishu-sync 获取 access token"""
    token_file = Path.home() / '.feishu' / 'access_token.json'
    if token_file.exists():
        data = json.loads(token_file.read_text(encoding='utf-8'))
        return data['access_token']
    raise RuntimeError(
        'Feishu token not found. Please run: python -m feishu_sync.retoken init_token'
    )


def update_record(app_token: str, table_id: str, record_id: str,
                  fields: dict, token: str) -> bool:
    """写回单条 Bitable 记录"""
    url = (f'https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}'
           f'/tables/{table_id}/records/{record_id}')
    body = json.dumps({'fields': fields}, ensure_ascii=False).encode('utf-8')
    headers = {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json; charset=utf-8',
    }
    req = urllib.request.Request(url, data=body, headers=headers, method='PUT')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
            if resp.get('code', -1) != 0:
                print(f'  API Error {resp.get("code")}: {resp.get("msg", "")}')
                return False
            return True
    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8', errors='replace')
        print(f'  HTTP {e.code}: {err[:120]}')
        return False
    except Exception as ex:
        print(f'  ERR {record_id}: {ex}')
        return False


# ─────────────────────────────────────────────────────────
# 关键词词表
# ─────────────────────────────────────────────────────────
FEATURE_NAMES = [
    'HNP', 'UNP', 'NDA', 'HNDA', 'Pilot', 'NOA', 'AEB', 'AEB-FB',
    'FCW', 'LDW', 'LDP', 'ELK', 'BSD', 'DOW', 'RCTA', 'IHC', 'MEB',
    'AMAP', 'ACC', 'TJA', 'LCC', 'CP', 'MNP', 'APA', 'RPA', 'HPA',
]
SCENARIO_KW = [
    '碰撞', '追尾', '变道', '超车', '刹停', '侧碰', '漂移', '画龙',
    '左偏', '右偏', '急刹', 'cut-in', 'CUTIN', '追撞', '行人', '动物',
    '障碍物', '豁口', '台阶', '地锁', '路沿', '柱子', '墙壁',
]
ROOT_CAUSE_KW = [
    '感知漏检', '感知延迟', '故障漏报', '故障未上报', '系统边界', '功能边界',
    'IMU零偏', 'EPS异常', '域控掉电', 'failsafe未报', '制动力不足',
    '感知检出晚', '降级未触发', '未打开降级', '感知置信度低',
]
SYS_SOLUTION_KW = [
    '故障诊断', '感知模型迭代', '感知算法', '功能安全', '信号上报',
    '系统降级', '控制策略', '制动能力', '功能边界',
]
ALERT_TYPE_KW = [
    '视觉告警', '语音告警', '震动告警', '三联告警', '红色告警', '仪表告警',
    '预警', '降级提醒', '接管提醒', '弹窗', '语音播报', '主动提示',
]
TRIGGER_KW = [
    'TTC', '置信度', '感知目标骤减', '从无到有', 'failsafe', '系统上限',
    '超出设计边界', '制动力达到', '目标突然出现', '变道后', '接管', '距离<',
]
SYS_KEYWORDS = [
    '故障诊断', '感知算法', '感知模型', '功能安全', 'failsafe', 'Failsafe',
    '算法迭代', '模型迭代', '感知迭代', '系统上限', '降级策略', '系统降级',
    '感知退化', '控制策略', '冗余', '上报', '检测上线',
]
HMI_KEYWORDS = [
    'HMI', '仪表', '文言', '告警', '预警', '弹窗', '语音', '音效', '播报',
    '震动', '图标', '接管', '降级提醒', '三联', '视觉', '提示', '红色',
]


# ─────────────────────────────────────────────────────────
# 行车碰撞 — 故障分类优化模板
# ─────────────────────────────────────────────────────────
DRIVING_TEMPLATES = {
    '故障诊断漏报/误报/延迟': (
        '【ADAS系统层面】①建立完整的感知/控制/传感器故障诊断上报链路，'
        '区分软硬件故障并分级上报；②制定故障持续时间阈值，防止误报；'
        '③增加冗余诊断通道，确保单一传感器降级时仍能上报系统状态'
    ),
    '未打开降级': (
        '【ADAS系统层面】①完善降级触发条件，'
        '在感知/执行能力低于设计阈值时自动进入降级模式；'
        '②降级决策逻辑需覆盖多传感器联合失效场景；'
        '③增加降级状态机可观测性，便于测试验证'
    ),
    '非故障相关': (
        '【ADAS系统层面】①感知模型迭代，扩大训练数据集覆盖弱势目标类型；'
        '②扩展系统设计包线，在接近边界前增加安全裕度；'
        '③规划层引入更保守的不确定性处理策略'
    ),
    '功能性能问题': (
        '【ADAS系统层面】①功能性能优化，提升目标检测精度和响应速度；'
        '②扩大功能工作包线，减少受限场景；'
        '③增加功能健康度自检，异常时主动限制激活'
    ),
    '超出系统边界': (
        '【ADAS系统层面】①在系统设计边界内增加安全裕度，边界预警机制前置；'
        '②明确系统 ODD（操作设计域）并在 HMI 中动态展示；'
        '③记录边界触发事件，驱动边界扩展迭代'
    ),
}
DRIVING_TEMPLATES['default'] = DRIVING_TEMPLATES['非故障相关']


# ─────────────────────────────────────────────────────────
# 泊车碰撞知识库
# ─────────────────────────────────────────────────────────
PARKING_KB = {
    '台阶': {
        'keywords': ['台阶', '高差', '坡道'],
        'scene': 'APA泊入过程中碰撞台阶/高差地面',
        'cause': '台阶属于低矮高对比差障碍物，纯视觉检出率低，超声波探测距离不足，感知模型对台阶/坡道场景覆盖不足',
        'sys':  '【ADAS系统层面】①感知模型迭代，增加台阶/地面高差样本训练；②融合超声波+视觉检出台阶场景；③对低矮高差场景建立专项感知能力评估',
        'hmi':  '【HMI交互层面】①泊位搜索阶段若检测到地面高度变化特征，主动提示"请注意：该区域可能存在台阶或高差，建议人工确认"；②泊车过程中触达台阶距离<30cm时，立即暂停并告警"检测到地面障碍，请手动确认"；③AVM界面标注高差疑似区域',
        'kw9':  '功能类[APA]；场景类[台阶, 高差]；根因类[感知漏检]；方案类[感知模型迭代]',
        'kw11': '功能类[APA]；告警类型[主动提示, 暂停告警]；触发条件[地面高差特征, 距离<30cm]',
    },
    '地锁': {
        'keywords': ['地锁', '限位', '地桩', '地杆'],
        'scene': 'APA泊入过程中碰撞地锁/限位器',
        'cause': '地锁体积小、金属材质，视觉检出率低；超声波在小目标近距离下存在盲区；感知模型对地锁/限位杆类目标覆盖不足',
        'sys':  '【ADAS系统层面】①增加地锁/金属小目标感知训练样本；②超声波与毫米波融合检测低矮金属目标；③扩大泊车感知弱势目标清单，标注地锁为高风险弱势场景',
        'hmi':  '【HMI交互层面】①进入停车场/地下车库场景时，主动播报"当前场景存在地锁/限位器风险，建议减速确认"；②AVM界面底部区域实时显示超声波距离数值辅助判断；③车速低于3km/h且前方距离<0.5m时告警暂停',
        'kw9':  '功能类[APA]；场景类[地锁, 限位器]；根因类[感知漏检]；方案类[感知模型迭代, 超声波融合]',
        'kw11': '功能类[APA]；告警类型[主动提示, 暂停告警]；触发条件[停车场场景, 距离<0.5m]',
    },
    '路沿': {
        'keywords': ['路沿', '路边石', '揉库', '路牙'],
        'scene': 'APA泊入/揉库过程中碰撞路沿/路边石',
        'cause': '路沿纵向距离估算误差；摄像头视角在近距离下存在视野盲区；感知对路沿连续性检出不稳定',
        'sys':  '【ADAS系统层面】①优化路沿纵向距离估计算法，加强立体视觉深度精度；②增加路沿连续性检测，防止端点误判；③在揉库场景下引入超声波辅助路沿定距',
        'hmi':  '【HMI交互层面】①AVM界面实时显示车辆四周与路沿的预测距离；②揉库/前进泊入时，距离路沿<20cm触发方向性告警音（前/后/左/右分区提示）；③当路沿处于视野盲区时，提示"前方/侧方视野有限，请减速确认路沿距离"',
        'kw9':  '功能类[APA]；场景类[路沿, 揉库]；根因类[感知漏检, 距离估算误差]；方案类[感知精度优化]',
        'kw11': '功能类[APA]；告警类型[方向性告警音, 视野提示]；触发条件[距离<20cm, 视野盲区]',
    },
    '消防箱': {
        'keywords': ['消防箱', '消防栓', '悬挂', '悬空', '突出物'],
        'scene': 'APA泊入过程中碰撞墙面悬挂物（消防箱/悬空障碍物）',
        'cause': '悬挂于墙面的障碍物位于超声波探测上限盲区，摄像头在贴近墙壁时无法完整识别悬空物体',
        'sys':  '【ADAS系统层面】①扩展感知检测高度范围，增加中高位悬挂障碍物检测；②感知输出障碍物高度信息，供规划层判断是否可通行；③建立悬空障碍物专项感知弱势场景',
        'hmi':  '【HMI交互层面】①靠近墙壁时（距离<0.5m）提示"墙面可能存在突出/悬挂障碍物，请人工确认"；②AVM界面对可疑悬空区域叠加警告标注；③最终停止位置提示驾驶员人工检查周围空间',
        'kw9':  '功能类[APA]；场景类[悬空障碍物, 消防箱]；根因类[感知漏检, 高位盲区]；方案类[感知高度扩展]',
        'kw11': '功能类[APA]；告警类型[主动提示, 视野告警]；触发条件[靠近墙壁, 距离<0.5m]',
    },
    '柱子': {
        'keywords': ['柱子', '矮柱', '停车柱', '水泥柱', '圆柱'],
        'scene': 'APA泊入过程中碰撞低矮柱子/停车场立柱',
        'cause': '柱子底部（<20cm高度）超声波存在探测盲区；视觉对圆柱体边缘估计存在误差；泊位紧邻柱子时安全裕量判断不准',
        'sys':  '【ADAS系统层面】①优化近距离柱子检测算法，结合超声波+视觉联合定位柱子边界；②建立泊车路径规划对柱子的安全裕量模型（≥15cm），不允许贴柱泊入；③柱子场景纳入泊车ODD限制，超出安全裕量时自动取消',
        'hmi':  '【HMI交互层面】①AVM界面对识别到的柱子高亮显示（蓝色轮廓线）；②泊车路径与柱子裕量<15cm时提示"前方存在立柱，请确认安全"；③泊车完成时若裕量<10cm，提示"车位较紧，请小心开门"',
        'kw9':  '功能类[APA]；场景类[柱子, 立柱]；根因类[感知漏检, 距离估算误差]；方案类[感知精度优化]',
        'kw11': '功能类[APA]；告警类型[视觉高亮, 安全提示]；触发条件[裕量<15cm]',
    },
    '障碍物': {
        'keywords': ['障碍物', '异形', '购物车', '三角锥', '水马', '隔离墩'],
        'scene': 'APA泊入过程中碰撞非规则形态障碍物',
        'cause': '异形障碍物（三角锥/购物车/水马）外形不规则，感知训练样本不足，检出率低；障碍物部分遮挡时更难识别',
        'sys':  '【ADAS系统层面】①扩大障碍物训练集，覆盖停车场常见异形障碍物类别；②引入点云占用栅格检测作为兜底，对任何未分类占用物采取保守策略；③建立停车场异形障碍物弱势目标清单',
        'hmi':  '【HMI交互层面】①当检测到不确定类型占用物时，显示"前方存在障碍物，正在确认中，请保持警惕"；②AVM界面对占用栅格区域进行红色填充提示；③停车过程中遇到不可识别障碍物，自动暂停并等待用户确认',
        'kw9':  '功能类[APA]；场景类[障碍物, 异形]；根因类[感知漏检]；方案类[感知模型迭代]',
        'kw11': '功能类[APA]；告警类型[不确定性提示, 暂停告警]；触发条件[未分类占用物]',
    },
    '墙壁': {
        'keywords': ['墙壁', '墙角', '死角', '侧墙', '后墙'],
        'scene': 'APA泊入过程中车辆后部/侧面碰撞墙壁',
        'cause': '贴近墙壁时摄像头和超声波均存在近距离盲区；倒车入位时后方墙壁距离估算在低速下精度不足',
        'sys':  '【ADAS系统层面】①融合多路超声波数据，减少单一超声波死角；②在低速（<3km/h）阶段增加感知采样频率，提升近距离精度；③建立停车位后方墙壁的虚拟边界模型',
        'hmi':  '【HMI交互层面】①AVM界面实时显示后方距离数值（精确到5cm）；②后方距离<0.3m时持续告警音，<0.15m时自动停止；③后退入位全程显示车辆与后方预计碰撞距离动态提示',
        'kw9':  '功能类[APA]；场景类[墙壁, 死角]；根因类[感知漏检, 距离估算误差]；方案类[超声波融合]',
        'kw11': '功能类[APA]；告警类型[持续告警音, 自动停止]；触发条件[距离<0.3m]',
    },
    '底盘': {
        'keywords': ['底盘', '斜坡', '减速带', '底部刮擦', '托底'],
        'scene': 'APA泊入过程中车辆底盘刮擦斜坡/减速带',
        'cause': '感知系统缺乏对地面起伏的高度感知能力；底盘高度与斜坡角度估算不足；规划层未考虑车辆最小离地间隙约束',
        'sys':  '【ADAS系统层面】①引入地面高程感知，检测斜坡坡度和减速带高度；②路径规划加入车辆底盘净空约束，超过安全坡度不执行泊入；③建立常见停车场斜坡/减速带场景感知能力评估',
        'hmi':  '【HMI交互层面】①检测到坡度>5°时，提示"前方存在坡道，底盘净空可能不足，建议人工确认"；②AVM界面对地面异常区域进行标注提示；③泊车完成后出现斜坡场景，提示"当前坡度较大，请确认车辆停放安全"',
        'kw9':  '功能类[APA]；场景类[底盘, 斜坡, 减速带]；根因类[感知漏检]；方案类[地面高程感知]',
        'kw11': '功能类[APA]；告警类型[坡度提示, 人工确认]；触发条件[坡度>5°]',
    },
    'RPA': {
        'keywords': ['RPA', '远程泊车', '手机泊车', '远程控制'],
        'scene': 'RPA远程泊车过程中碰撞障碍物或操作不当',
        'cause': 'RPA场景下用户对车辆实时状态感知受限（仅依赖手机屏幕），HMI反馈信息不足；用户介入时机和方式不明确',
        'sys':  '【ADAS系统层面】①RPA场景增加更保守的安全包络，自动停止距离提前至0.5m；②加强RPA感知鲁棒性，弱势目标自动降低速度；③建立RPA异常退出机制，异常立即停止并告警',
        'hmi':  '【HMI交互层面】①手机端实时显示车辆四周障碍物距离和AVM画面；②检测到障碍物时手机振动+语音+弹窗三联提示，并暂停泊车；③清晰提示用户接管时机：弹窗显示"请确认环境安全后继续"并需要用户主动确认才恢复',
        'kw9':  '功能类[RPA]；场景类[远程泊车]；根因类[感知漏检]；方案类[感知模型迭代]',
        'kw11': '功能类[RPA]；告警类型[三联告警, 手机振动]；触发条件[障碍物检测, 距离<0.5m]',
    },
    'HPA': {
        'keywords': ['HPA', '记忆泊车', 'AVP', '自动泊车辅助', '学习泊车'],
        'scene': 'HPA记忆泊车过程中场景变化导致碰撞',
        'cause': 'HPA依赖历史地图，场景动态变化（障碍物增加/移位）时检测不足；地图更新机制不及时',
        'sys':  '【ADAS系统层面】①HPA实时感知叠加历史地图，动态障碍物优先采用实时感知；②场景差异超过阈值时自动降级为人工确认模式；③提升HPA地图更新频率，定期重学习',
        'hmi':  '【HMI交互层面】①HPA启动时提示"正在比对历史路径，如场景有较大变化请注意安全"；②检测到场景与历史地图差异>30%时，弹窗提示"当前场景与历史记录差异较大，建议重新学习或人工泊车"；③HPA过程中障碍物告警优先级高于路径跟随',
        'kw9':  '功能类[HPA]；场景类[记忆泊车, 场景变化]；根因类[感知漏检]；方案类[感知模型迭代]',
        'kw11': '功能类[HPA]；告警类型[场景差异提示, 降级告警]；触发条件[场景差异>30%]',
    },
    '故障': {
        'keywords': ['故障', '传感器异常', '超声波故障', '摄像头故障', '域控', '掉电', '重启'],
        'scene': 'APA/RPA泊车过程中传感器或系统故障导致碰撞',
        'cause': '传感器故障未及时上报和显示；系统降级逻辑未触发；驾驶员对系统故障状态无感知',
        'sys':  '【ADAS系统层面】①完善泊车系统传感器健康监测，任一传感器故障立即触发系统降级；②域控掉电/重启场景建立安全保护机制，保证车辆原地停止；③故障分级管理：P0故障立即禁止功能，P1故障限制速度并告警',
        'hmi':  '【HMI交互层面】①传感器故障时仪表/中控立即弹出"XXX传感器异常，泊车功能已暂停，请人工接管"；②AVM界面故障传感器区域用灰色阴影标注，清晰指示盲区范围；③系统恢复正常后主动提示用户可重新激活功能',
        'kw9':  '功能类[APA, RPA]；场景类[系统故障]；根因类[故障漏报]；方案类[故障诊断, 系统降级]',
        'kw11': '功能类[APA, RPA]；告警类型[故障弹窗, 仪表告警]；触发条件[传感器故障, 系统降级]',
    },
}


def match_parking_kb(ticket: str, remark: str) -> dict:
    """根据工单和备注匹配泊车知识库"""
    text = (ticket + ' ' + remark).lower()
    for scenario, info in PARKING_KB.items():
        for kw in info['keywords']:
            if kw.lower() in text:
                return info
    # 默认匹配「障碍物」
    return PARKING_KB['障碍物']


# ─────────────────────────────────────────────────────────
# 工单事件提取
# ─────────────────────────────────────────────────────────
def parse_ticket_event(ticket: str) -> str:
    ticket = ticket.strip()
    # 格式: XXXXX-MK-NNNN# YYYYMMDD-City - EventDescription
    m = re.search(r'[-#]\s*\d{6,8}[-\s]+.+?[-–—]\s*(.+)$', ticket)
    if m:
        return m.group(1).strip()
    # 格式: PREFIX-YYYYMMDD-ID-EventDescription
    m = re.search(r'\d{8}[-\s]+\S+[-\s]+(.+)$', ticket)
    if m:
        return m.group(1).strip()
    # 取最后一个 - 后的内容
    parts = re.split(r'[-–—]', ticket)
    if len(parts) >= 2:
        return parts[-1].strip()
    return ticket[:80]


# ─────────────────────────────────────────────────────────
# 行车记录分析
# ─────────────────────────────────────────────────────────
def analyze_driving_record(fields: dict, cfg) -> dict:
    """行车碰撞记录：生成/优化 6 个目标字段"""
    hmi_plan = gs(fields, cfg.hmi_field)
    if not hmi_plan:
        return {}

    ticket   = gs(fields, cfg.ticket_field)
    remark   = gs(fields, cfg.remark_field)
    fault    = gs(fields, cfg.fault_field)
    level2   = gs(fields, cfg.l2_field)
    level3   = gs(fields, cfg.l3_field)
    validate = gs(fields, cfg.validate_field)

    sentences = re.split(r'[。；；\n]', hmi_plan)
    sentences = [s.strip() for s in sentences if s.strip()]

    # ── 事故场景 ──
    event = parse_ticket_event(ticket)
    first_sent = sentences[0] if sentences else ''
    if event and first_sent and event not in first_sent:
        scene = f'{event}。{first_sent}'
    elif event:
        scene = event
    else:
        scene = first_sent

    # ── 事故原因 ──
    cause_parts = []
    if remark:
        cause_parts.append(remark)
    if level2 and level2 not in ('NA', ''):
        cause_parts.append(level2)
    if level3 and level3 not in ('NA', ''):
        cause_parts.append(level3)
    if fault and fault not in ('非故障相关', ''):
        cause_parts.append(fault)
    for s in sentences[:4]:
        if any(kw in s for kw in ['原因', '导致', '异常', '漏检', '漏报', '失效', '不足']):
            cause_parts.append(s)
            break
    cause = '；'.join(dict.fromkeys(p for p in cause_parts if p))

    # ── 文本8：ADAS 系统方案 ──
    tpl = DRIVING_TEMPLATES.get(fault, DRIVING_TEMPLATES['default'])
    sys_sents = [s for s in sentences if any(k in s for k in SYS_KEYWORDS)]
    text8 = tpl
    if sys_sents:
        text8 += f'；原始方案：{"；".join(sys_sents[:2])}'
    if validate:
        text8 += f'；【验证方式】{validate}'

    # ── 文本9：文本8 关键词 ──
    combined8 = text8 + ' ' + hmi_plan
    feats   = [f for f in FEATURE_NAMES   if f in combined8]
    scenes  = [k for k in SCENARIO_KW     if k in combined8]
    roots   = [k for k in ROOT_CAUSE_KW   if k in combined8]
    sols    = [k for k in SYS_SOLUTION_KW if k in text8]
    kw9_parts = []
    if feats:  kw9_parts.append(f'功能类[{", ".join(feats)}]')
    if scenes: kw9_parts.append(f'场景类[{", ".join(scenes)}]')
    if roots:  kw9_parts.append(f'根因类[{", ".join(roots)}]')
    if sols:   kw9_parts.append(f'方案类[{", ".join(sols)}]')
    text9 = '；'.join(kw9_parts) if kw9_parts else hmi_plan[:60]

    # ── 文本10：HMI 交互方案 ──
    hmi_sents = [s for s in sentences if any(k in s for k in HMI_KEYWORDS)]
    if hmi_sents:
        text10 = '【HMI交互层面】' + '；'.join(hmi_sents[:4])
    else:
        text10 = '【HMI交互层面】' + hmi_plan[:200]

    # ── 文本11：文本10 关键词 ──
    combined10 = text10 + ' ' + hmi_plan
    feats10  = [f for f in FEATURE_NAMES if f in combined10]
    alerts   = [k for k in ALERT_TYPE_KW if k in combined10]
    triggers = [k for k in TRIGGER_KW    if k in combined10]
    kw11_parts = []
    if feats10:  kw11_parts.append(f'功能类[{", ".join(feats10)}]')
    if alerts:   kw11_parts.append(f'告警类型[{", ".join(alerts)}]')
    if triggers: kw11_parts.append(f'触发条件[{", ".join(triggers)}]')
    text11 = '；'.join(kw11_parts) if kw11_parts else text10[:80]

    return {
        cfg.scene_field:  scene[:500],
        cfg.cause_field:  cause[:300],
        cfg.text8_field:  text8[:800],
        cfg.text9_field:  text9[:300],
        cfg.text10_field: text10[:800],
        cfg.text11_field: text11[:300],
    }


# ─────────────────────────────────────────────────────────
# 泊车记录分析
# ─────────────────────────────────────────────────────────
def analyze_parking_record(fields: dict, cfg) -> dict:
    """泊车碰撞记录：从知识库生成全量字段"""
    ticket = gs(fields, cfg.ticket_field)
    remark = gs(fields, cfg.remark_field)

    kb = match_parking_kb(ticket, remark)
    scene = kb['scene']
    cause = kb['cause']

    validate = gs(fields, cfg.validate_field)
    text8 = kb['sys']
    if validate:
        text8 += f'；【验证方式】{validate}'

    text9  = kb['kw9']
    text10 = kb['hmi']
    text11 = kb['kw11']

    hmi_plan = f"{kb['sys']}；{kb['hmi']}"

    return {
        cfg.hmi_field:    hmi_plan[:1000],  # 同时补全 HMI方案
        cfg.scene_field:  scene[:500],
        cfg.cause_field:  cause[:300],
        cfg.text8_field:  text8[:800],
        cfg.text9_field:  text9[:300],
        cfg.text10_field: text10[:800],
        cfg.text11_field: text11[:300],
    }


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────
def main():
    cfg = parse_args()

    # 解析数据文件
    data_file = cfg.data_file or str(Path.home() / 'bitable_raw.json')
    if not os.path.exists(data_file):
        print(f'ERROR: 数据文件不存在: {data_file}')
        print('请先运行: feishu-sync-cli read_page "<bitable_url>" --force_refresh > ~/bitable_raw.json')
        sys.exit(1)

    raw = json.load(open(data_file, encoding='utf-8'))
    records = raw.get('records', [])

    # 从数据文件获取 app_token（如果 bitable_url 未能直接解析）
    app_token = raw.get('_app_token', '')
    table_id  = raw.get('_table_id', '')
    if not app_token:
        app_token, table_id = parse_bitable_url(cfg.bitable_url)
    if not app_token:
        print('ERROR: 无法解析 app_token。请确保数据文件包含 _app_token 字段，或提供完整 bitable URL')
        sys.exit(1)

    # 分类记录
    driving_cats = set(cfg.driving_cats.split(','))
    parking_cat  = cfg.parking_cat

    driving_recs = []
    parking_recs = []
    for rec in records:
        f = rec['fields']
        func = gs(f, cfg.func_field)
        hmi  = gs(f, cfg.hmi_field)
        if func in driving_cats and hmi:
            driving_recs.append(rec)
        elif func == parking_cat and not hmi:
            parking_recs.append(rec)

    print(f'行车碰撞记录（有HMI方案）: {len(driving_recs)} 条')
    print(f'泊车碰撞记录（无HMI方案）: {len(parking_recs)} 条')

    # 确定处理列表
    to_process = []
    if cfg.mode in ('auto', 'driving', 'all'):
        to_process += [('driving', r) for r in driving_recs]
    if cfg.mode in ('auto', 'parking'):
        to_process += [('parking', r) for r in parking_recs]
    if cfg.mode == 'all':
        to_process += [('parking', r) for r in parking_recs]

    if cfg.limit > 0:
        to_process = to_process[:cfg.limit]

    print(f'本次处理: {len(to_process)} 条 | mode={cfg.mode} | dry_run={cfg.dry_run}')

    if cfg.dry_run:
        print('\n===== 干运行预览（前5条）=====')
        for i, (rtype, rec) in enumerate(to_process[:5]):
            fields = rec['fields']
            if rtype == 'driving':
                patch = analyze_driving_record(fields, cfg)
            else:
                patch = analyze_parking_record(fields, cfg)
            print(f'\n[{i+1}] {rec["record_id"]} ({rtype})')
            print(f'  工单: {gs(fields, cfg.ticket_field)[:60]}')
            for k, v in patch.items():
                print(f'  {k}: {str(v)[:80]}')
        return

    token = get_token()
    ok_count = fail_count = 0

    for i, (rtype, rec) in enumerate(to_process):
        rec_id = rec['record_id']
        fields = rec['fields']

        if rtype == 'driving':
            patch = analyze_driving_record(fields, cfg)
        else:
            patch = analyze_parking_record(fields, cfg)

        if not patch:
            continue

        ok = update_record(app_token, table_id, rec_id, patch, token)
        if ok:
            ok_count += 1
        else:
            fail_count += 1

        if (i + 1) % 30 == 0:
            print(f'  进度: {i+1}/{len(to_process)} | ok={ok_count} fail={fail_count}')
            time.sleep(0.3)

    print(f'\n===== 完成 | 成功: {ok_count}, 失败: {fail_count} =====')


if __name__ == '__main__':
    main()
