import geopandas as gpd
import xarray as xr
import rioxarray
from rioxarray.exceptions import NoDataInBounds
import os
import glob

# --- 1. 设置文件和文件夹路径 ---
gpkg_path = "data/bbox_study_areas.gpkg" 
raster_dir = "data/ESA_CCI_LC_reclassified"  
output_dir = "data/clipped_basins_esa/"
os.makedirs(output_dir, exist_ok=True)

basin_layers = ['tevere', 'po', 'ebro', 'crati']
search_pattern = os.path.join(raster_dir, "*.nc")
raster_files = glob.glob(search_pattern)

print(f"总共找到了 {len(raster_files)} 份 ESA .nc 影像。")

# --- 2. 开始批量处理 ---
for nc_file in raster_files:
    file_name = os.path.basename(nc_file)
    name_without_ext = os.path.splitext(file_name)[0] 
    
    print(f"\n=======================================")
    print(f"开始处理: {file_name}")
    
    try:
        ds = xr.open_dataset(nc_file)
        
        # 提取名叫 'lccs_class' 的变量
        if 'lccs_class' in ds.data_vars:
            rds = ds['lccs_class']
        else:
            var_name = list(ds.data_vars)[0]
            rds = ds[var_name]
            
        x_dim = 'lon' if 'lon' in rds.dims else ('x' if 'x' in rds.dims else rds.dims[-1])
        y_dim = 'lat' if 'lat' in rds.dims else ('y' if 'y' in rds.dims else rds.dims[-2])
        rds = rds.rio.set_spatial_dims(x_dim=x_dim, y_dim=y_dim)
        
        # 【关键修改 1】：赋予正确的原始坐标系 EPSG:4326 (WGS84)
        rds.rio.write_crs("EPSG:4326", inplace=True)
        raster_crs = rds.rio.crs
        
        # --- 3. 循环裁剪流域 ---
        for layer_name in basin_layers:
            basin_gdf = gpd.read_file(gpkg_path, layer=layer_name)
            
            # 统一矢量与栅格的坐标系用于裁剪 (都在 4326 下裁剪)
            if basin_gdf.crs != raster_crs:
                basin_gdf = basin_gdf.to_crs(raster_crs)
                
            try:
                # 裁剪
                clipped = rds.rio.clip(basin_gdf.geometry, basin_gdf.crs, drop=True)
                
                # 【关键修改 2】：裁剪后，重投影到 EPSG:3035 以符合项目后续面积计算要求
                clipped_3035 = clipped.rio.reproject("EPSG:3035")
                
                output_filename = f"{name_without_ext}_{layer_name}.tif"
                output_filepath = os.path.join(output_dir, output_filename)
                
                # 保存为 .tif
                clipped_3035.rio.to_raster(output_filepath)
                print(f"  [成功] -> 已裁剪并重投影保存为: {output_filename}")
                
            except NoDataInBounds:
                print(f"  [跳过] -> 影像不包含 {layer_name} 流域的范围")
            except Exception as e:
                print(f"  [出错] -> 裁剪 {layer_name} 失败: {e}")
                
    except Exception as e:
        print(f"无法读取文件 {file_name}: {e}")