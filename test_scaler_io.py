"""
最小单元测试脚本：scaler保存与加载测试
运行方式：终端 python test_scaler_io.py

注意：scaler 会写入临时目录，不污染 output/model_weight/ 下的正式模型权重。
"""
import tempfile
from pathlib import Path

import numpy as np

import feature_engineer.sequence_builder as sb
from feature_engineer.sequence_builder import SequenceBuilder

# 将 scaler 输出重定向到临时目录，避免测试污染正式模型权重目录
_MODEL_WEIGHT_DIR = Path(tempfile.mkdtemp(prefix='scaler_test_'))
sb.MODEL_WEIGHT_DIR = _MODEL_WEIGHT_DIR


def test_case_1_generic_scaler():
    """测试用例1：save_path=None，触发兜底，生成 scaler_generic.pkl"""
    print("==========【测试1：兜底通用scaler】==========")
    # 1.构造模拟时序数据
    n_sample = 100
    seq_len = 12
    n_feature = 6
    X_train = np.random.rand(n_sample, seq_len, n_feature)
    X_test = np.random.rand(20, seq_len, n_feature)

    # =========修复点：实例化！=========
    builder = SequenceBuilder()
    X_train_norm, X_test_norm, scaler_origin = builder.normalize(
        X_train=X_train,
        X_test=X_test,
        save_path=None
    )

    generic_pkl = _MODEL_WEIGHT_DIR / "scaler_generic.pkl"
    print(f"文件预期输出路径：{generic_pkl}")

    if generic_pkl.exists():
        print("✅ 文件成功写入磁盘")
    else:
        print("❌ 文件没有生成！save_scaler逻辑异常")
        return False

    scaler_load = SequenceBuilder.load_scaler(generic_pkl)
    print("✅ pickle文件加载完成")

    test_data = np.array([[0.1, 0.3, 0.5, 0.6, 0.2, 0.8]])
    result_origin = scaler_origin.transform(test_data)
    result_load = scaler_load.transform(test_data)

    if np.allclose(result_origin, result_load):
        print("🎉测试1通过：保存-加载计算结果完全一致\n")
        return True
    else:
        print(f"❌测试1失败：origin={result_origin}, load={result_load}\n")
        return False


def test_case_2_equipment_scaler():
    """测试用例2：正式业务场景：传入设备ID的路径 scaler_equipment_01.pkl"""
    print("==========【测试2：设备专属scaler】==========")
    n_sample = 100
    seq_len = 12
    n_feature = 6
    X_train = np.random.rand(n_sample, seq_len, n_feature)
    X_test = np.random.rand(20, seq_len, n_feature)

    equipment_id = "equipment_01"
    equip_pkl_path = _MODEL_WEIGHT_DIR / f"scaler_{equipment_id}.pkl"

    # =========修复点：实例化=========
    builder = SequenceBuilder()
    X_train_norm, X_test_norm, scaler_origin = builder.normalize(
        X_train=X_train,
        X_test=X_test,
        save_path=equip_pkl_path
    )

    if equip_pkl_path.exists():
        print(f"✅设备专属文件生成成功：{equip_pkl_path}")
    else:
        print("❌设备pkl文件未生成")
        return False

    scaler_load = SequenceBuilder.load_scaler(equip_pkl_path)

    test_data = np.array([[0.1, 0.3, 0.5, 0.6, 0.2, 0.8]])
    result_origin = scaler_origin.transform(test_data)
    result_load = scaler_load.transform(test_data)

    if np.allclose(result_origin, result_load):
        print("🎉测试2通过：设备scaler保存加载正常\n")
        return True
    else:
        print(f"❌测试2失败\n")
        return False


if __name__ == "__main__":
    print("开始运行 scaler IO最小测试脚本\n")
    res1 = test_case_1_generic_scaler()
    res2 = test_case_2_equipment_scaler()
    print("====全部测试执行完毕====")
    if res1 and res2:
        print("✅全部测试用例通过，scaler读写模块无问题，可以交给业务调用！")
    else:
        print("⚠️部分测试失败，请检查sequence_builder.py代码")
