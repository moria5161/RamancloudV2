#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
拉曼光谱去鬼峰脚本

宇宙射线在拉曼光谱谱图中表现为随机分布的强且峰宽极窄的信号，
其出峰位置随光栅位置而变，因此常常被称为鬼峰。

使用方法:
1. 在下方 CONFIG 区域设置参数
2. 运行: python despike.py
"""

import os
import sys
import glob
import numpy as np
from pathlib import Path

# Add raman_web to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'raman_web'))

# 忽略算法模块的静默警告
from algorithms.despike import despike_spectrum, identify_cosmic_rays  #type: ignore
from algorithms.common import read_spectrum, write_spectrum, detect_delimiter  # type: ignore


# ============================================================================
# 配置参数 - 在此修改
# ============================================================================

CONFIG = {
    # 输入设置
    'input_path': './鬼峰数据/*.txt',      # 输入文件路径（支持通配符，如 './data/*.txt'）
                                                # 或单个文件路径，如 './data/spectrum.txt'
    
    # 输出设置
    'output_dir': './despiked_spectra',         # 输出目录
    'output_suffix': '_despiked',               # 输出文件名后缀（单文件模式时使用）
    
    # 去鬼峰参数
    'threshold': None,                          # 峰检测阈值(相对高度差 >= 此值才被认为是潜在峰)
                                                # None: 自动计算（中位数 + 15*MAD）
                                                # 或手动指定数值，如 100.0
    
    'fwhm_threshold': 4,                      # 半高宽阈值（数据点数）
                                                # 小于此值的峰被判定为鬼峰
                                                
    
    'interpolation': 'linear',                  # 插值方法
                                                # 可选: 'linear', 'quadratic', 'cubic'
                                                # 默认: 'linear'
    
    # 显示设置
    'verbose': True,                            # 是否显示详细信息
    
    # 可视化设置
    'show_plot': True,                          # 处理完成后是否显示结果图
    'save_plot': True,                          # 是否保存结果图为PNG
    'plot_dir': './despiked_plots',             # 结果图保存目录
}

# ============================================================================


def plot_results(
    wavenumbers: np.ndarray,
    original_spectrum: np.ndarray,
    corrected_spectrum: np.ndarray,
    cosmic_rays: list,
    save_path: str = None,
    show: bool = True
) -> None:
    """
    绘制去鬼峰前后对比图
    
    包含两个子图:
      上方: 原始谱图 + 标记的鬼峰位置（红色圆点）
      下方: 去鬼峰后的谱图
    
    Args:
        wavenumbers: 拉曼位移数据
        original_spectrum: 原始谱图
        corrected_spectrum: 去鬼峰后的谱图
        cosmic_rays: 鬼峰信息列表
        save_path: 图片保存路径（None则不保存）
        show: 是否显示图片
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("  警告: 未安装 matplotlib，无法生成可视化结果")
        return
    
    # 设置中文字体（如果可用），否则回退到英文
    for font_name in ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei', 'Arial Unicode MS']:
        try:
            plt.rcParams['font.sans-serif'] = [font_name] + plt.rcParams['font.sans-serif']
            plt.rcParams['axes.unicode_minus'] = False
            # 测试字体是否有效
            fig_test, ax_test = plt.subplots()
            ax_test.set_title('测试 Test')
            plt.close(fig_test)
            break
        except:
            continue
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    
    # --- Top subplot: Original spectrum + cosmic ray markers ---
    ax1.plot(wavenumbers, original_spectrum, 'b-', linewidth=1.5, label='Original spectrum')
    
    # Mark cosmic ray positions (red dots)
    if cosmic_rays:
        cr_indices = [cr['peak_idx'] for cr in cosmic_rays]
        cr_x = wavenumbers[cr_indices]
        cr_y = original_spectrum[cr_indices]
        ax1.scatter(cr_x, cr_y, color='red', s=60, zorder=5,
                    marker='o', edgecolors='darkred', linewidths=1,
                    label=f'Cosmic rays ({len(cosmic_rays)})')
        
        # Add vertical dashed lines at cosmic ray positions
        for idx in cr_indices:
            ax1.axvline(x=wavenumbers[idx], color='red', linestyle='--',
                        alpha=0.3, linewidth=0.8)
    
    ax1.set_ylabel('Intensity')
    ax1.set_title('Original Spectrum with Cosmic Ray Markers', fontsize=15, fontweight='bold')
    ax1.legend(loc='upper right', fontsize=9)
    ax1.grid(True, alpha=0.3)
    
    # --- Bottom subplot: Corrected spectrum ---
    ax2.plot(wavenumbers, corrected_spectrum, 'g-', linewidth=1.5, label='After despiking')
    ax2.set_xlabel('Raman Shift (cm$^{-1}$)', fontsize=15)
    ax2.set_ylabel('Intensity')
    ax2.set_title('Despiked Spectrum', fontsize=15, fontweight='bold')
    ax2.legend(loc='upper right', fontsize=10)
    ax2.grid(True, alpha=0.3)
    
    # Overall title
    fig.suptitle('Raman Spectrum Despike Comparison', fontsize=15, fontweight='bold', y=1.02)
    
    plt.tight_layout()
    
    # 保存图片
    if save_path:
        os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else '.', exist_ok=True)
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  结果图保存至: {save_path}")
    
    # 显示图片
    if show:
        plt.show()
    else:
        plt.close(fig)


def process_file(
    input_path: str,
    output_path: str,
    threshold: float = None,
    fwhm_threshold: float = 2.0,
    interpolation: str = 'linear',
    verbose: bool = False
) -> dict:
    """
    处理单个光谱文件，去除鬼峰
    
    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径
        threshold: 峰检测阈值（None为自动计算）
        fwhm_threshold: 半高宽阈值
        interpolation: 插值方法
        verbose: 是否显示详细信息
    
    Returns:
        处理结果字典
    """
    # 读取光谱数据
    wavenumbers, spectrum = read_spectrum(input_path)
    spectrum = np.array(spectrum, dtype=np.float64)
    wavenumbers = np.array(wavenumbers, dtype=np.float64)
    
    # 去鬼峰处理
    result = despike_spectrum(
        spectrum,
        threshold=threshold,
        fwhm_threshold=fwhm_threshold,
        interpolation=interpolation,
        return_info=True
    )
    
    # 写入输出文件
    write_spectrum(output_path, wavenumbers, result['corrected_spectrum'])
    
    if verbose:
        print(f"  检测到 {result['num_cosmic_rays']} 个鬼峰")
        for i, cr in enumerate(result['cosmic_rays']):
            print(f"    鬼峰 {i+1}: 位置索引={cr['peak_idx']}, "
                  f"FWHM={cr['fwhm']:.2f}, 强度={cr['intensity']:.2f}")
    
    return {
        **result,
        'wavenumbers': wavenumbers,
    }


def main():
    """主函数"""
    print("=" * 60)
    print("拉曼光谱去鬼峰处理")
    print("=" * 60)
    
    # 显示配置信息
    print("配置参数:")
    print(f"  输入路径: {CONFIG['input_path']}")
    print(f"  输出目录: {CONFIG['output_dir']}")
    print(f"  峰检测阈值: {CONFIG['threshold'] if CONFIG['threshold'] else '自动计算'}")
    print(f"  半高宽阈值: {CONFIG['fwhm_threshold']}")
    print(f"  插值方法: {CONFIG['interpolation']}")
    print(f"  详细信息: {'是' if CONFIG['verbose'] else '否'}")
    print(f"  显示结果图: {'是' if CONFIG['show_plot'] else '否'}")
    print(f"  保存结果图: {'是' if CONFIG['save_plot'] else '否'}")
    print("=" * 60)
    
    # 收集输入文件
    input_pattern = CONFIG['input_path']
    if '*' in input_pattern:
        input_files = glob.glob(input_pattern)
    else:
        input_files = [input_pattern]
    
    if not input_files:
        print(f"错误: 未找到输入文件 - {input_pattern}")
        sys.exit(1)
    
    print(f"找到 {len(input_files)} 个文件")
    
    # 创建输出目录
    output_dir = CONFIG['output_dir']
    os.makedirs(output_dir, exist_ok=True)
    
    # 处理统计
    total_cosmic_rays = 0
    total_time = 0
    success_count = 0
    
    # 处理每个文件
    for input_path in input_files:
        input_path = os.path.abspath(input_path)
        basename = os.path.basename(input_path)
        
        # 生成输出文件名
        name, ext = os.path.splitext(basename)
        output_filename = f"{name}{CONFIG['output_suffix']}{ext}"
        output_path = os.path.join(output_dir, output_filename)
        
        print(f"\n处理: {input_path}")
        
        try:
            result = process_file(
                input_path,
                output_path,
                threshold=CONFIG['threshold'],
                fwhm_threshold=CONFIG['fwhm_threshold'],
                interpolation=CONFIG['interpolation'],
                verbose=CONFIG['verbose']
            )
            total_cosmic_rays += result['num_cosmic_rays']
            total_time += result['processing_time']
            success_count += 1
            #print(f"  -> {output_path} ({result['processing_time']:.3f}s)")
            
            # 可视化结果
            if CONFIG['show_plot'] or CONFIG['save_plot']:
                wavenumbers = result['wavenumbers']
                original = result.get('original_spectrum', None)
                if original is None:
                    # 如果是批处理模式，用当前文件重新读取原始数据
                    # 但实际上 process_file 返回的 result 里没有原始光谱
                    # 需要从原始文件读取
                    _, original_spectrum = read_spectrum(input_path)
                    original = np.array(original_spectrum, dtype=np.float64)
                
                corrected = result['corrected_spectrum']
                cosmic_rays = result['cosmic_rays']
                
                # 确定保存路径
                save_path = None
                if CONFIG['save_plot']:
                    plot_dir = CONFIG['plot_dir']
                    plot_name = f"{name}_result.png"
                    save_path = os.path.join(plot_dir, plot_name)
                
                # 绘制
                plot_results(
                    wavenumbers, original, corrected, cosmic_rays,
                    save_path=save_path,
                    show=CONFIG['show_plot']
                )
                
        except Exception as e:
            print(f"  错误: {e}")
    
    # 汇总信息
    # print("\n" + "=" * 60)
    # print("处理完成!")
    # print(f"  成功处理: {success_count}/{len(input_files)} 个文件")
    # print(f"  总鬼峰数: {total_cosmic_rays}")
    # print(f"  总耗时: {total_time:.3f}s")
    # print(f"  输出目录: {os.path.abspath(output_dir)}")
    # if CONFIG['save_plot']:
    #     print(f"  结果图目录: {os.path.abspath(CONFIG['plot_dir'])}")
    # print("=" * 60)

if __name__ == '__main__':
    main()