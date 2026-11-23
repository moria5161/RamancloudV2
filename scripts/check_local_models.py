"""Read-only installation check; does not train or start any model workers."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
from structure_profiles import public_configuration
from peaknet_package import configuration
from ssnet_contract import runtime_ready


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    checks = {
        '结构生成 / Vib2Mol 原版': public_configuration('official')['ready'],
        '库匹配 / PeakNet + AirNet': configuration()[2],
        '混合物解析 / SSnet 运行环境': runtime_ready(),
    }
    for label, ready in checks.items():
        print(('已安装' if ready else '未安装') + ' | ' + label)
    print(('已安装' if public_configuration('agent')['ready'] else '未安装（可选）') + ' | Vib2Mol Agent 扩展')
    print('只检查安装文件是否齐备；权重内容在实际运行时校验。SSnet 标准品模型需另行训练，不包含在此检查中。')
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
