import os
import math
import random
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio  # Only used for coordinate transformation (transform.xy)
import fiona
import re
# Core libraries for processing NetCDF (.nc) files
import xarray as xr
import rioxarray

# ==========================================
# 1. Global Setup & Class Definitions
# ==========================================
basin_gpkg = "data/bbox_study_areas.gpkg"

# Target mapping dictionary (Including subclasses for 'Other')
target_mapping = {
        20: 'Forest', 5: 'Shrubland', 7: 'Grassland', 8: 'Cropland', 9:"Other",11:"Other",12:"Other", 13:"Other",16:"Other",
        15: 'Water_bodies (Excluded)', 255: 'No Data (Excluded)'
    }

# Define the sampling pools and their corresponding pixel codes
pool_definitions = {
    'Forest':    [20],
    'Shrubland': [5],
    'Grassland': [7],
    'Cropland':  [8],
    'Other':     [9, 11, 12, 16, 13]
}

# ==========================================
# 2. Core Logic: Dynamic Quota Calculation
# ==========================================
def calculate_dynamic_quotas(raster_data):
    print("\n" + "="*60)
    print(" 🧮 [DEBUG] Starting Detailed Dynamic Quota Calculation ")
    print("="*60)
    
    # Step 1: Calculate theoretical total sample size using Cochran's formula
    Z = 1.96  # 95% Confidence Level
    e = 0.05  # 5% Margin of Error
    U = 0.5   # Conservative expected accuracy (maximizes variance)
    total_n = math.ceil((Z**2 * U * (1 - U)) / (e**2))
    print(f"[Step 1] Theoretical total sample size (Cochran's formula): {total_n} points\n")
    
    # Step 2: Count actual valid pixels for each pool on the map
    pixel_counts = {}
    total_valid_pixels = 0
    print("[Step 2] Counting actual pixels for each class within the basin:")
    for pool_name, codes in pool_definitions.items():
        count = np.sum(np.isin(raster_data, codes))
        pixel_counts[pool_name] = count
        total_valid_pixels += count
        print(f"  -> {pool_name} (Codes {codes}): Found {count} pixels")
        
    print(f"  -> [Total Valid Pixels] (Base for allocation): {total_valid_pixels} pixels\n")
    
    # Step 3: Initial proportional allocation and triggering CEOS minimum threshold
    final_quotas = {}
    guaranteed_points = 0
    remaining_classes = []
    remaining_pixels = 0
    
    print("[Step 3] Calculating initial area proportions and applying CEOS minimum threshold (>=50 points):")
    for pool_name, count in pixel_counts.items():
        if total_valid_pixels == 0:
            print("  -> 🚨 Error: No valid pixels found in the basin!")
            return {}
            
        proportion = count / total_valid_pixels
        initial_quota_float = total_n * proportion
        
        print(f"  -> {pool_name}:")
        print(f"     * Area proportion: {proportion*100:.2f}%")
        print(f"     * Theoretical points: {initial_quota_float:.2f} points")
        
        if initial_quota_float < 50:
            final_quotas[pool_name] = 50
            guaranteed_points += 50
            print(f"     * ⚠️ Minimum Triggered! Bumped up to: 50 points")
        else:
            remaining_classes.append(pool_name)
            remaining_pixels += count
            print(f"     * ✅ Proceeding to major classes reallocation pool.")
            
    # Step 4: Reallocate remaining points among the major classes
    points_left_to_distribute = total_n - guaranteed_points
    print(f"\n[Step 4] Second round reallocation (Distributing among major classes):")
    print(f"  -> Points consumed by minimums: {guaranteed_points}")
    print(f"  -> Remaining points available: {points_left_to_distribute}")
    print(f"  -> Major classes participating: {remaining_classes}")
    
    for pool_name in remaining_classes:
        relative_prop = pixel_counts[pool_name] / remaining_pixels
        calculated_points_float = points_left_to_distribute * relative_prop
        final_quotas[pool_name] = round(calculated_points_float)
        
        print(f"  -> {pool_name}:")
        print(f"     * Relative proportion: {relative_prop*100:.2f}%")
        print(f"     * Reallocation math: {points_left_to_distribute} * {relative_prop:.4f} = {calculated_points_float:.2f}")
        print(f"     * Assigned points (rounded): {final_quotas[pool_name]} points")
            
    # Step 5: Fix rounding errors to ensure the sum exactly matches total_n
    print("\n[Step 5] Checking and fixing rounding errors:")
    current_total = sum(final_quotas.values())
    difference = total_n - current_total
    print(f"  -> Current sum of allocated points: {current_total}")
    
    if difference != 0:
        largest_class = max(remaining_classes, key=lambda k: pixel_counts[k])
        print(f"  -> Error detected: {difference} point(s). Compensating largest class [{largest_class}].")
        final_quotas[largest_class] += difference
    else:
        print("  -> Perfect distribution without errors, no compensation needed.")
        
    print(f"\n🎯 [Final Quotas] : {final_quotas}")
    print(f"🎯 [Overall Validation] : Sum of all quotas = {sum(final_quotas.values())} (Must equal {total_n})")
    print("="*60 + "\n")
    
    return final_quotas

# ==========================================
# 3. Stratified Sampling & File Generation
# ==========================================
def generate_true_stratified_points():
    # 1. Prepare basin vector boundaries
    basin_gdf = gpd.read_file(basin_gpkg, layer=target_basin)
    geom = basin_gdf.geometry.values[0]
    
    collected_data = []
    point_id = 1
    
    print(f"\n--- Loading Raster file via xarray ---")
    # 2. Robust file reading logic (automatically adapts to .nc and .tif)
    try:
        if reference_raster_path.lower().endswith(('.tif', '.tiff')):
            # If it's a TIFF file, force the use of rasterio engine
            ds = xr.open_dataset(reference_raster_path, engine="rasterio")
        else:
            # If it's a NetCDF file, force the use of netcdf4 engine
            ds = xr.open_dataset(reference_raster_path, decode_coords="all", engine="netcdf4")
    except Exception as e:
        print(f"🚨 Failed to read file completely! Please check if the file is corrupted: {reference_raster_path}")
        raise e
    
    # Extract the first variable data
    var_name = list(ds.data_vars)[0]
    print(f"Dataset detected. Using first data variable: '{var_name}'")
    rds = ds[var_name]
    
    # Force rioxarray to recognize the spatial dimensions
    rds = rds.rio.write_coordinate_system()

    # 3. Process and unify CRS
    src_crs = rds.rio.crs
    if src_crs is None:
        print("⚠️ Warning: NetCDF lacks explicit CRS metadata. Assuming EPSG:4326.")
        rds.rio.write_crs("EPSG:4326", inplace=True)
        src_crs = rds.rio.crs

    if basin_gdf.crs != src_crs:
        print("Projecting basin geometry to match NetCDF CRS...")
        basin_gdf = basin_gdf.to_crs(src_crs)
        geom = basin_gdf.geometry.values[0]

    # 4. Clip the NC raster based on the basin boundary
    print("Masking NetCDF to the basin boundary...")
    clipped = rds.rio.clip([geom], basin_gdf.crs, drop=True)
    raster_data = clipped.values
    
    # Reduce to a 2D array (y, x) for subsequent sampling
    if raster_data.ndim == 3:
        raster_data = raster_data[0]
        
    out_transform = clipped.rio.transform()
    
    # 5. Call the function above to print the complete quota calculation process
    dynamic_quotas = calculate_dynamic_quotas(raster_data)
    
    # 6. Start spatial sampling
    print("\n--- Starting precision spatial sampling on the map ---")
    for pool_name, valid_codes in pool_definitions.items():
        quota = dynamic_quotas.get(pool_name, 0)
        if quota == 0:
            continue
            
        row_indices, col_indices = np.where(np.isin(raster_data, valid_codes))
        available_pixels = list(zip(row_indices, col_indices))
        
        total_available = len(available_pixels)
        if total_available < quota:
            print(f"    ⚠️ Warning: Only {total_available} pixels available for {pool_name}. Taking all.")
            sampled_pixels = available_pixels
        else:
            sampled_pixels = random.sample(available_pixels, quota)
        
        for row, col in sampled_pixels:
            # Use affine transformation matrix to convert matrix indices to geographic coordinates
            x_coord, y_coord = rasterio.transform.xy(out_transform, row, col)
            actual_map_code = raster_data[row, col]
            
            collected_data.append({
                'Point_ID': f"{target_basin.upper()}_GT_{point_id:03d}",
                'Map_Class_Code': actual_map_code,
                'Map_Class_Name': target_mapping.get(actual_map_code, 'Unknown'),
                'X_Coord': x_coord,
                'Y_Coord': y_coord,
                'GT_Class_Code': '', 
                'Notes': ''          
            })
            point_id += 1
        print(f"    ✅ Successfully sampled {len(sampled_pixels)} points for {pool_name}.")
            
    return pd.DataFrame(collected_data), src_crs

# ==========================================
# 4. Main function: Batch generate ESA sampling point CSVs
# ==========================================
if __name__ == "__main__":
    # Set the root directory for data storage
    esa_root_dir = "data/ESA_CCI_LC_reclassified"
    
    # Define the four major basins array
    all_basins = ["crati", "ebro", "po", "tevere"]
    
    print(f"--- 🚀 Starting single-source (ESA) batch sampling pipeline (Four major basins | Folder classified storage) ---")

    # Outer layer: Iterate through basins
    for current_basin in all_basins:
        print(f"\n" + "★"*60)
        print(f" 🌍 Processing basin: {current_basin.upper()}")
        
        # Create an exclusive folder for the current basin
        output_folder = f"results_esa_only_{current_basin}"
        os.makedirs(output_folder, exist_ok=True)
        print(f" 📂 Output directory is ready: {output_folder}")
        print("★"*60)
        
        # Dynamically update global variables
        global target_basin
        target_basin = current_basin
        
        # Inner layer: Year loop
        for year in range(1980, 2027):
            year_str = str(year)
            
            # 1. Only fuzzy match ESA year files
            try:
                esa_files = [f for f in os.listdir(esa_root_dir) if re.search(year_str, f)]
            except FileNotFoundError:
                continue

            # 2. If ESA data for that year exists, execute
            if esa_files:
                print(f"\n  [{current_basin.upper()} | {year_str}] ESA data found! Starting sampling...")
                
                # Update path global variables
                global reference_raster_path
                reference_raster_path = os.path.join(esa_root_dir, esa_files[0])
                
                # Execute original sampling logic
                df_points, original_crs = generate_true_stratified_points()
                
                # Handle coordinate transformation to WGS84
                gdf_export = gpd.GeoDataFrame(df_points, geometry=gpd.points_from_xy(df_points.X_Coord, df_points.Y_Coord), crs=original_crs)
                gdf_export_4326 = gdf_export.to_crs("EPSG:4326")
                
                df_points['Longitude'] = gdf_export_4326.geometry.x
                df_points['Latitude'] = gdf_export_4326.geometry.y
                df_points.drop(columns=['X_Coord', 'Y_Coord'], inplace=True)
                
                # Append the output path to the corresponding folder
                file_name = f"ground_truth_samples_{current_basin}_{year_str}_ESA_only.csv"
                current_output_csv = os.path.join(output_folder, file_name)
                
                # Organize the final column order (all GLC-related columns removed)
                final_columns = [
                    'Point_ID', 'Longitude', 'Latitude', 
                    'Map_Class_Code', 'Map_Class_Name', 
                    'GT_Class_Code', 'Notes'
                ]
                df_final = df_points[final_columns]
                
                # Save to the exclusive folder
                df_final.to_csv(current_output_csv, index=False)
                print(f"    ✅ ESA sampling complete and saved to folder: {current_output_csv}")
                
            else:
                continue

    print("\n🎉 Task successfully completed! All independent ESA sampling files have been classified by basin and stored in their respective results_xxx folders.")