import rasterio
import numpy as np
import pandas as pd
import os
import glob
import re

# ==========================================
# 1. 设置基础参数
# ==========================================
basins = ['tevere', 'po', 'ebro', 'crati']
esa_dir = "data/clipped_basins_esa/"
glc_dir = "data/clipped_basins_glc/"

molca_classes = {
    20: 'Forest',
    5: 'Shrubland',
    7: 'Grassland',
    8: 'Cropland',
    9: 'Wetland',
    11: 'Lichens & Mosses',
    12: 'Bareland',
    13: 'Built-up',
    15: 'Water',
    16: 'Ice/Snow'
}

# ==========================================
# 2. 定义批量提取并生成 DataFrame 的函数
# ==========================================
def generate_area_dataframe(folder_path, basins, is_esa=True):
    print(f"正在扫描文件夹: {folder_path}")
    all_data = [] 
    
    all_years = set()
    for basin in basins:
        search_pattern = os.path.join(folder_path, f"*{basin}.tif")
        for tif_path in glob.glob(search_pattern):
            match = re.search(r'(19\d{2}|20\d{2})', os.path.basename(tif_path))
            if match:
                all_years.add(int(match.group(1)))
    
    sorted_years = sorted(list(all_years))
    
    for basin in basins:
        print(f"  -> 正在处理流域: {basin}")
        
        # 【核心修改点 1】：把键名改成 Notebook 期待的 'Study area' 和 'Land cover class'
        basin_class_data = {
            class_code: {'Study area': basin, 'Land cover class': class_name} 
            for class_code, class_name in molca_classes.items()
        }
        
        for class_code in molca_classes:
            for year in sorted_years:
                basin_class_data[class_code][year] = 0.0
                
        search_pattern = os.path.join(folder_path, f"*{basin}.tif")
        tif_files = glob.glob(search_pattern)
        
        for tif_path in tif_files:
            match = re.search(r'(19\d{2}|20\d{2})', os.path.basename(tif_path))
            if not match:
                continue
            year = int(match.group(1))
            
            with rasterio.open(tif_path) as src:
                data = src.read(1)
                
                pixel_area_m2 = 90000 if is_esa else 900
                
                for class_code in molca_classes:
                    pixel_count = np.sum(data == class_code)
                    area_m2 = pixel_count * pixel_area_m2
                    basin_class_data[class_code][year] = area_m2
                    
        for class_code in molca_classes:
            all_data.append(basin_class_data[class_code])
            
    df = pd.DataFrame(all_data)
    
    # 【核心修改点 2】：强制排序列名，确保前两列的名字完全吻合 Notebook 的要求
    cols = ['Study area', 'Land cover class'] + sorted_years
    df = df[cols]
    
    return df

# ==========================================
# 3. 执行提取并导出为 Notebook 兼容的 CSV
# ==========================================
print("\n=== 开始处理 ESA CCI LC 数据 ===")
df_esa = generate_area_dataframe(esa_dir, basins, is_esa=True)
df_esa.to_csv("esa_cci_class_area.csv", sep=';', decimal=',', index=False)
print("✅ 成功生成: esa_cci_class_area.csv")

print("\n=== 开始处理 GLC_FCS30 数据 ===")
df_glc = generate_area_dataframe(glc_dir, basins, is_esa=False)
df_glc.to_csv("glc_fcs30_class_area.csv", sep=';', decimal=',', index=False)
print("✅ 成功生成: glc_fcs30_class_area.csv")

print("\n🎉 表头已完美修复！请回到 Jupyter Notebook 重新运行！")