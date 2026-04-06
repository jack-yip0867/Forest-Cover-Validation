import pandas as pd
import geopandas as gpd
import rasterio
import os
import glob
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix

# ==========================================
# 1. 核心参数设置 (请核对)
# ==========================================
target_year = 2015  # 【重要】请修改为你刚刚在 Google Earth 中查看的历史年份！
csv_file = "./ground_truth_samples.csv"
esa_dir = "data/clipped_basins_esa/"
glc_dir = "data/clipped_basins_glc/"

molca_dict = {
    20: 'Forest', 5: 'Shrubland', 7: 'Grassland', 8: 'Cropland', 
    9: 'Wetland', 11: 'Lichens', 12: 'Bareland', 13: 'Built-up', 
    15: 'Water', 16: 'Ice/Snow'
}

# ==========================================
# 2. 读取你的“答题卡”并转换为地理数据
# ==========================================
print(f"正在加载 {target_year} 年的地面真实数据...")
df = pd.read_csv(csv_file)

# 清理空数据并确保类型为整数
df = df.dropna(subset=['True_Class'])
df['True_Class'] = df['True_Class'].astype(int)

# 将经纬度转换为 GeoDataFrame (设置原始坐标系为 WGS84 EPSG:4326)
gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.Longitude, df.Latitude), crs="EPSG:4326")

# ==========================================
# 3. 定义“像素提取”功能（自动处理坐标系对齐）
# ==========================================
def extract_raster_values(gdf, raster_dir, year):
    predictions = []
    for idx, row in gdf.iterrows():
        basin = row['Basin']
        geom = row.geometry
        
        # 寻找对应年份和流域的影像
        search_pattern = os.path.join(raster_dir, f"*{year}*{basin}*.tif")
        files = glob.glob(search_pattern)
        
        if not files:
            predictions.append(-1) # 找不到文件
            continue
            
        with rasterio.open(files[0]) as src:
            # 【核心科技】：自动将经纬度点投影到该影像的专属坐标系中 (无论是 3035 还是 4326)
            point_proj = gpd.GeoSeries([geom], crs="EPSG:4326").to_crs(src.crs).iloc[0]
            
            # 在该坐标点上“戳”下去提取像素值
            try:
                val = list(src.sample([(point_proj.x, point_proj.y)]))[0][0]
                predictions.append(val)
            except:
                predictions.append(-1) # 点可能落在了影像边缘外
                
    return predictions

# ==========================================
# 4. 执行提取并计算得分
# ==========================================
print("正在从 ESA 和 GLC 影像中提取对应的卫星预测值...")
df['ESA_Class'] = extract_raster_values(gdf, esa_dir, target_year)
df['GLC_Class'] = extract_raster_values(gdf, glc_dir, target_year)

# 过滤掉提取失败的点 (比如边界处的空值)
df_valid = df[(df['ESA_Class'] > 0) & (df['GLC_Class'] > 0)]
print(f"成功匹配了 {len(df_valid)} 个有效验证点！\n")

# 提取三列用于计算
y_true = df_valid['True_Class']
y_esa = df_valid['ESA_Class']
y_glc = df_valid['GLC_Class']

# 计算总体精度 (Overall Accuracy) 和 F1分数 (Macro average)
esa_oa = accuracy_score(y_true, y_esa)
glc_oa = accuracy_score(y_true, y_glc)

esa_f1 = f1_score(y_true, y_esa, average='macro', zero_division=0)
glc_f1 = f1_score(y_true, y_glc, average='macro', zero_division=0)

print(f"🏆 ESA CCI LC (300m) - 总体精度(OA): {esa_oa:.2%}, F1-Score: {esa_f1:.4f}")
print(f"🏆 GLC_FCS30 (30m)  - 总体精度(OA): {glc_oa:.2%}, F1-Score: {glc_f1:.4f}\n")

# ==========================================
# 5. 绘制酷炫的混淆矩阵 (Confusion Matrix)
# ==========================================
# 获取这批点中出现过的所有独特类别并排序
labels = sorted(list(set(y_true) | set(y_esa) | set(y_glc)))
target_names = [molca_dict.get(l, str(l)) for l in labels]

fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# 画 ESA 混淆矩阵
cm_esa = confusion_matrix(y_true, y_esa, labels=labels)
sns.heatmap(cm_esa, annot=True, fmt='d', cmap='Blues', ax=axes[0], 
            xticklabels=target_names, yticklabels=target_names, cbar=False)
axes[0].set_title(f'ESA CCI LC (300m) Confusion Matrix\nOA: {esa_oa:.1%}', fontsize=14)
axes[0].set_xlabel('Satellite Predicted Class', fontsize=12)
axes[0].set_ylabel('True Class (Ground Truth)', fontsize=12)

# 画 GLC 混淆矩阵
cm_glc = confusion_matrix(y_true, y_glc, labels=labels)
sns.heatmap(cm_glc, annot=True, fmt='d', cmap='Greens', ax=axes[1], 
            xticklabels=target_names, yticklabels=target_names, cbar=False)
axes[1].set_title(f'GLC_FCS30 (30m) Confusion Matrix\nOA: {glc_oa:.1%}', fontsize=14)
axes[1].set_xlabel('Satellite Predicted Class', fontsize=12)
axes[1].set_ylabel('True Class (Ground Truth)', fontsize=12)

plt.tight_layout()
plt.show()