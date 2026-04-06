import rasterio
import numpy as np
import matplotlib.pyplot as plt
import os
import glob
import re

# ==========================================
# 1. 设置基础参数
# ==========================================
# 你想要分析的流域名称 (可以换成 'po', 'ebro', 'crati')
basin_name = "tevere" 
# 森林在 MOLCA 图例中的代码是 20
target_class_code = 20  

# 你的两个裁剪好的文件夹路径 (请确保路径准确)
esa_dir = "data/clipped_basins_esa/"
glc_dir = "data/clipped_basins_glc/"

# ==========================================
# 2. 定义一个面积计算的通用函数
# ==========================================
def calculate_class_area(folder_path, basin, class_code):
    """
    遍历文件夹中的TIF文件，提取年份，统计特定类别的面积 (km²)
    """
    # 寻找以该流域名称结尾的 tif 文件
    search_pattern = os.path.join(folder_path, f"*{basin}.tif")
    tif_files = glob.glob(search_pattern)
    
    # 用字典来保存 {年份: 面积}，方便后续排序
    area_data = {}
    
    for tif_path in tif_files:
        filename = os.path.basename(tif_path)
        
        # 使用正则表达式提取文件名中的 4 位数字年份 (如 1992, 2015)
        match = re.search(r'(19\d{2}|20\d{2})', filename)
        if not match:
            continue
        year = int(match.group(1))
        
        # 打开影像计算面积
        with rasterio.open(tif_path) as src:
            data = src.read(1)
            # 统计目标类别的像素个数
            pixel_count = np.sum(data == class_code)
            
            # 动态获取当前影像的像素物理尺寸 (X方向分辨率 * Y方向分辨率的绝对值)
            pixel_area_m2 = src.res[0] * abs(src.res[1])
            
            # 计算总面积 (平方米 -> 平方公里)
            total_area_km2 = (pixel_count * pixel_area_m2) / 1_000_000
            
            area_data[year] = total_area_km2
            
    # 按年份将字典排序，拆分成 X (年份) 和 Y (面积) 两个列表
    sorted_years = sorted(area_data.keys())
    sorted_areas = [area_data[y] for y in sorted_years]
    
    return sorted_years, sorted_areas

# ==========================================
# 3. 分别计算 ESA 和 GLC 的森林面积
# ==========================================
print(f"正在计算 {basin_name.capitalize()} 流域的森林面积...")

esa_years, esa_areas = calculate_class_area(esa_dir, basin_name, target_class_code)
print(f"ESA 数据提取完成: 包含从 {min(esa_years)} 到 {max(esa_years)} 的 {len(esa_years)} 个年份。")

glc_years, glc_areas = calculate_class_area(glc_dir, basin_name, target_class_code)
print(f"GLC 数据提取完成: 包含从 {min(glc_years)} 到 {max(glc_years)} 的 {len(glc_years)} 个年份。")


# ==========================================
# 4. 绘制多产品对比折线图
# ==========================================
plt.figure(figsize=(12, 6))

# 画 ESA 的线 (因为是每年连续的，用实线)
plt.plot(esa_years, esa_areas, marker='o', linestyle='-', color='dodgerblue', 
         linewidth=2, markersize=5, label='ESA CCI LC (300m)')

# 画 GLC 的线 (因为有年份跳跃，折线图会自动连接，同样加点以示区分)
plt.plot(glc_years, glc_areas, marker='s', linestyle='--', color='forestgreen', 
         linewidth=2, markersize=5, label='GLC_FCS30 (30m)')

# 设置图表装饰
plt.title(f"Forest Area Comparison in {basin_name.capitalize()} Basin\n(ESA CCI vs GLC_FCS30)", fontsize=15, fontweight='bold')
plt.xlabel("Year", fontsize=12)
plt.ylabel("Forest Area ($km^2$)", fontsize=12)
plt.legend(fontsize=11)
plt.grid(True, linestyle=':', alpha=0.7)

# 优化 X 轴显示，让刻度更密集但不重叠
all_years = sorted(list(set(esa_years + glc_years)))
plt.xticks(all_years[::2], rotation=45) # 每隔一年显示一个刻度，倾斜45度

plt.tight_layout()
plt.show()