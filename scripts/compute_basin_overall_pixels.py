import os
import glob
import re
import numpy as np
import pandas as pd
import geopandas as gpd
import xarray as xr
import rioxarray
import rasterio
import rasterio.mask 
from rioxarray.exceptions import NoDataInBounds

# ==========================================
# 1. Global Parameters Setup
# ==========================================
basins = ['tevere', 'po', 'ebro', 'crati']
gpkg_path = "data/bbox_study_areas.gpkg" 

# Directories for raw ESA (.nc) and GLC (.tif) files
esa_raw_dir = "data/ESA_CCI_LC_reclassified"  
glc_raw_dir = "data/glc-fcs30"

# Standardized 10-class MOLCA legend specification
molca_classes = {
    20: 'Forest', 5: 'Shrubland', 7: 'Grassland', 8: 'Cropland',
    9: 'Wetland', 11: 'Lichens & Mosses', 12: 'Bareland', 
    13: 'Built-up', 15: 'Water', 16: 'Ice/Snow'
}

# ==========================================
# 2. Engine A: In-memory processing for ESA (.nc)
# ==========================================
def process_esa_nc_to_dataframe():
    print(f"\n[Engine A] Starting direct processing for ESA CCI LC (.nc)...")
    all_data = {class_code: {basin: {} for basin in basins} for class_code in molca_classes}
    all_years = set()
    
    nc_files = glob.glob(os.path.join(esa_raw_dir, "*.nc"))
    
    for nc_file in nc_files:
        match = re.search(r'(19\d{2}|20\d{2})', os.path.basename(nc_file))
        if not match: continue
        year = int(match.group(1))
        all_years.add(year)
        
        print(f"  -> Parsing ESA year: {year}...")
        try:
            ds = xr.open_dataset(nc_file)
            rds = ds['lccs_class'] if 'lccs_class' in ds.data_vars else ds[list(ds.data_vars)[0]]
            
            x_dim = 'lon' if 'lon' in rds.dims else ('x' if 'x' in rds.dims else rds.dims[-1])
            y_dim = 'lat' if 'lat' in rds.dims else ('y' if 'y' in rds.dims else rds.dims[-2])
            rds = rds.rio.set_spatial_dims(x_dim=x_dim, y_dim=y_dim)
            
            # Enforce native WGS84 projection
            rds.rio.write_crs("EPSG:4326", inplace=True)
            
            for basin in basins:
                basin_gdf = gpd.read_file(gpkg_path, layer=basin)
                if basin_gdf.crs != rds.rio.crs:
                    basin_gdf = basin_gdf.to_crs(rds.rio.crs)
                
                try:
                    clipped = rds.rio.clip(basin_gdf.geometry, basin_gdf.crs, drop=True)
                    clipped_3035 = clipped.rio.reproject("EPSG:3035")
                    
                    data_array = clipped_3035.values
                    for class_code in molca_classes:
                        pixel_count = np.sum(data_array == class_code)
                        all_data[class_code][basin][year] = pixel_count * 90000
                except NoDataInBounds:
                    pass
        except Exception as e:
            print(f"Error processing ESA {year}: {e}")
            
    return format_to_dataframe(all_data, sorted(list(all_years)))

# ==========================================
# 3. Engine B: Memory-Safe processing for GLC (.tif)
# ==========================================
def process_glc_tif_to_dataframe():
    print(f"\n[Engine B] Starting memory-safe processing for massive GLC_FCS30 (.tif)...")
    all_data = {class_code: {basin: {} for basin in basins} for class_code in molca_classes}
    all_years = set()
    
    tif_files = glob.glob(os.path.join(glc_raw_dir, "*.tif"))
    
    for tif_path in tif_files:
        match = re.search(r'(19\d{2}|20\d{2})', os.path.basename(tif_path))
        if not match: continue
        year = int(match.group(1))
        all_years.add(year)
        
        print(f"  -> Surgical cropping GLC year: {year} (Safe RAM mode)...")
        try:
            # 使用 rasterio 直接打开硬盘映射，而不是把数据塞进内存
            with rasterio.open(tif_path) as src:
                for basin in basins:
                    basin_gdf = gpd.read_file(gpkg_path, layer=basin)
                    
                    # 确保矢量和栅格坐标系一致
                    if basin_gdf.crs != src.crs:
                        basin_gdf = basin_gdf.to_crs(src.crs)
                    
                    try:
                        # 【核心黑科技】：只从硬盘上抠出边界内的数据，极大节省内存
                        clipped_data, _ = rasterio.mask.mask(src, basin_gdf.geometry, crop=True)
                        
                        for class_code in molca_classes:
                            # 统计像素个数
                            pixel_count = np.sum(clipped_data == class_code)
                            
                            if year not in all_data[class_code][basin]:
                                all_data[class_code][basin][year] = 0
                                
                            # GLC spatial resolution is ~30m (900 m2)
                            all_data[class_code][basin][year] += pixel_count * 900
                            
                    except ValueError:
                        # 当流域矢量和当前这块影像没有重叠时，会触发这个错误，直接跳过即可
                        pass
        except Exception as e:
            print(f"Error processing GLC {year}: {e}")

    return format_to_dataframe(all_data, sorted(list(all_years)))

# ==========================================
# 4. Formatting Tool: Convert to Jupyter-compatible DataFrame
# ==========================================
def format_to_dataframe(raw_data_dict, years):
    formatted_list = []
    for class_code, class_name in molca_classes.items():
        for basin in basins:
            row = {'Study area': basin, 'Land cover class': class_name}
            for year in years:
                row[year] = raw_data_dict[class_code][basin].get(year, 0.0)
            formatted_list.append(row)
            
    df = pd.DataFrame(formatted_list)
    cols = ['Study area', 'Land cover class'] + years
    return df[cols]

# ==========================================
# 5. Main Execution
# ==========================================
if __name__ == "__main__":
    df_esa = process_esa_nc_to_dataframe()
    df_esa.to_csv("esa_cci_class_area.csv", sep=';', decimal=',', index=False)
    print("✅ Successfully generated: esa_cci_class_area.csv")

    df_glc = process_glc_tif_to_dataframe()
    df_glc.to_csv("glc_fcs30_class_area.csv", sep=';', decimal=',', index=False)
    print("✅ Successfully generated: glc_fcs30_class_area.csv")
    
    print("\n🎉 Data extraction pipeline completely refactored. Zero intermediate files generated!")