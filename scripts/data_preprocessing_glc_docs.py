import geopandas as gpd
import rasterio
from rasterio.mask import mask
import os
import glob

# --- 1. 设置文件和文件夹路径 ---
gpkg_path = "./data/bbox_study_areas.gpkg" 

# 【重要修改 1】：这里填入你截图里那个包含所有 GLC_FCS30 影像的“文件夹”路径
# 比如："C:/Users/.../GLC_FCS30D_reclassified/"
raster_dir = "./data/glc-fcs30"  

output_dir = "./data/clipped_basins_glc/"
os.makedirs(output_dir, exist_ok=True)

basin_layers = ['tevere', 'po', 'ebro', 'crati']

# --- 2. 找到文件夹下所有的 .tif 文件 ---
# glob.glob 会返回一个包含所有符合条件的文件路径的列表
search_pattern = os.path.join(raster_dir, "*.tif")
raster_files = glob.glob(search_pattern)

print(f"总共找到了 {len(raster_files)} 份待处理的栅格影像。")

# --- 3. 双重循环：外层循环遍历每一年份的影像，内层循环遍历四个流域 ---
for raster_path in raster_files:
    # 提取当前处理的文件名 (比如 "GLC_FCS30_2010_mosa..." )，用来给输出文件命名
    file_name = os.path.basename(raster_path)
    name_without_ext = os.path.splitext(file_name)[0] 
    
    print(f"\n=======================================")
    print(f"开始处理影像: {file_name}")
    print(f"=======================================")
    
    with rasterio.open(raster_path) as src:
        raster_crs = src.crs
        
        for layer_name in basin_layers:
            # 读取当前流域边界
            basin_gdf = gpd.read_file(gpkg_path, layer=layer_name)
            
            # 检查并统一坐标系
            if basin_gdf.crs != raster_crs:
                basin_gdf = basin_gdf.to_crs(raster_crs)
                
            geom = [basin_gdf.geometry.iloc[0]]
            
            try:
                # 1. 裁剪 (在原始 4326 下裁剪)
                out_image, out_transform = mask(src, geom, crop=True)
                
                # ... (中间更新 out_meta 的部分不变) ...
                
                # 将裁剪出来的数组转成 rioxarray 对象，方便重投影
                import xarray as xr
                import rioxarray
                
                # 构建 DataArray
                da = xr.DataArray(out_image, dims=("band", "y", "x"))
                da.rio.write_crs(raster_crs, inplace=True) # 告诉它原来是 4326
                da.rio.write_transform(out_transform, inplace=True)
                
                # 2. 【核心添加】：重投影到 3035
                da_3035 = da.rio.reproject("EPSG:3035")
                
                # 3. 保存
                output_filename = f"{name_without_ext}_{layer_name}.tif"
                output_filepath = os.path.join(output_dir, output_filename)
                da_3035.rio.to_raster(output_filepath)
                
                print(f"  [成功] -> 已裁剪并重投影到3035: {output_filename}")
                
            except ValueError as e:
                # 影像如果不覆盖该流域，会报 ValueError，我们捕获它并跳过
                print(f"  [跳过] -> 影像不包含 {layer_name} 流域的范围")