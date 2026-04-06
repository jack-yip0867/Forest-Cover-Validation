import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import Point
import os

# --- 1. 设置参数 ---
gpkg_path = "data/bbox_study_areas.gpkg" 
basins = ['tevere', 'po', 'ebro', 'crati']

# 【关键修改】：将每个流域的抽样点从 50 改为了 20
# 总共 80 个点。人工看图大概只需要 10-15 分钟即可完成预实验
points_per_basin = 20 

all_points = []

print("正在生成流域随机抽样点 (预实验版)，请稍候...")

# --- 2. 在每个流域内生成随机点 ---
for basin in basins:
    # 读取流域边界
    gdf = gpd.read_file(gpkg_path, layer=basin)
    # 投影到 EPSG:3035，确保在公制面积下均匀撒点
    gdf_proj = gdf.to_crs("EPSG:3035")
    polygon = gdf_proj.geometry.iloc[0]
    
    minx, miny, maxx, maxy = polygon.bounds
    count = 0
    
    while count < points_per_basin:
        # 在外接矩形内随机生成坐标
        pnt = Point(np.random.uniform(minx, maxx), np.random.uniform(miny, maxy))
        # 确认这个点确实落在不规则的流域边界内部
        if polygon.contains(pnt):
            # 将点转换回 WGS84 经纬度 (因为谷歌地球只认经纬度)
            pnt_wgs84 = gpd.GeoSeries([pnt], crs="EPSG:3035").to_crs("EPSG:4326").iloc[0]
            
            all_points.append({
                'Point_ID': f"{basin}_{count+1}",
                'Basin': basin,
                'Longitude': pnt_wgs84.x,
                'Latitude': pnt_wgs84.y,
                'True_Class': '' # 这里留空，作为你的答题区！
            })
            count += 1

df_points = pd.DataFrame(all_points)

# --- 3. 导出为 CSV 答题卡 ---
csv_path = "ground_truth_samples.csv"
df_points.to_csv(csv_path, index=False)
print(f"✅ 成功生成答题卡: {csv_path}")

# --- 4. 导出为 KML 谷歌地球文件 ---
kml_path = "ground_truth_samples.kml"
kml_header = '<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2">\n<Document>\n'
kml_footer = '</Document>\n</kml>'

with open(kml_path, "w", encoding="utf-8") as f:
    f.write(kml_header)
    for _, row in df_points.iterrows():
        f.write(f'  <Placemark>\n')
        f.write(f'    <name>{row["Point_ID"]}</name>\n')
        f.write(f'    <Point>\n')
        f.write(f'      <coordinates>{row["Longitude"]},{row["Latitude"]},0</coordinates>\n')
        f.write(f'    </Point>\n')
        f.write(f'  </Placemark>\n')
    f.write(kml_footer)

print(f"✅ 成功生成地标文件: {kml_path}")