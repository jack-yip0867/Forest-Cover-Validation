import os
import numpy as np
import pandas as pd
# Import plotting libraries
import matplotlib.pyplot as plt
import seaborn as sns

# ==========================================
# 1. Basic Configuration
# ==========================================
all_basins = ["crati", "ebro", "po", "tevere"]

# We use ESA as the Reference/Ground Truth, and GLC as the Prediction
# (Even if it is just a cross-comparison, we need to define a direction to calculate PA and UA)
reference_col = 'Map_Class_Name'  # ESA classification (as reference)
prediction_col = 'GLC_Class_Name' # GLC classification (as prediction)

print("--- 🚀 Starting fully automated remote sensing accuracy assessment pipeline (Outputting confusion matrix images only) ---")

# ==========================================
# 2. Core Processing Loop
# ==========================================
for basin in all_basins:
    input_folder = f"results_{basin}"
    output_folder = f"metrics_{basin}"
    
    # Check if the data folder for this basin exists
    if not os.path.exists(input_folder):
        print(f"⚠️ Data folder {input_folder} not found, skipping automatically.")
        continue

    # Create an independent Metrics folder
    os.makedirs(output_folder, exist_ok=True)
    print(f"\n" + "="*50)
    print(f" 📊 Processing basin: {basin.upper()}")
    print(f" 📁 Report output directory: {output_folder}")
    print("="*50)

    # Iterate through each CSV file in the basin's folder
    for file_name in os.listdir(input_folder):
        if not file_name.endswith('.csv'):
            continue
            
        file_path = os.path.join(input_folder, file_name)
        
        # Extract year and base name (e.g., ground_truth_samples_crati_2015_ESA_final.csv -> crati_2015)
        base_name = file_name.replace('.csv', '')
        
        # Read data
        df = pd.read_csv(file_path)
        
        # Ensure there are no NaN values in both columns
        df = df.dropna(subset=[reference_col, prediction_col])
        if df.empty:
            continue

        # ==========================================
        # Step A: Calculate and plot Confusion Matrix image
        # ==========================================
        # Extract all categories that appeared to ensure the matrix is symmetric
        labels = sorted(list(set(df[reference_col].unique()) | set(df[prediction_col].unique())))
        
        # Use pandas.crosstab to calculate Cross-tabulation
        cm = pd.crosstab(
            df[reference_col], 
            df[prediction_col], 
            rownames=['ESA_Reference'], 
            colnames=['GLC_Prediction'],
            dropna=False
        ).reindex(index=labels, columns=labels, fill_value=0)
        
        # Remove CSV output, directly use seaborn to plot the confusion matrix heatmap image
        # Set canvas size
        plt.figure(figsize=(10, 8))
        # annot=True displays values, fmt='d' formats values as integers, cmap sets color palette
        # xticklabels, yticklabels set axis labels to land cover type names
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=labels, yticklabels=labels)
        
        plt.xlabel('Prediction (GLC)')
        plt.ylabel('Reference (ESA)')
        plt.title(f'Confusion Matrix: {base_name}')
        plt.tight_layout() # Prevent labels from being cut off

        # Define image output path
        cm_img_path = os.path.join(output_folder, f"{base_name}_confusion_matrix.png")
        # Save image, dpi sets resolution
        plt.savefig(cm_img_path, dpi=300)
        # Close plot, release memory
        plt.close()

        # ==========================================
        # Step B: Calculate Standard Error Statistics
        # ==========================================
        # Extract diagonal (number of consistent/correct classifications)
        correct = np.diag(cm)
        total_ref = cm.sum(axis=1).values  # Sum of each row (Total of ESA)
        total_pred = cm.sum(axis=0).values # Sum of each column (Total of GLC)
        total_samples = cm.values.sum()    # Total samples (usually 385)

        # Calculate Producer Accuracy (PA, Recall) - avoid division by 0
        pa = np.where(total_ref > 0, correct / total_ref, 0)
        
        # Calculate User Accuracy (UA, Precision) - avoid division by 0
        ua = np.where(total_pred > 0, correct / total_pred, 0)
        
        # Calculate F1-Score
        f1 = np.where((pa + ua) > 0, 2 * (pa * ua) / (pa + ua), 0)
        
        # Calculate Overall Accuracy (OA)
        oa = correct.sum() / total_samples if total_samples > 0 else 0

        # Organize results into a DataFrame
        stats_df = pd.DataFrame({
            'Land_Cover_Class': labels,
            'Total_Reference_ESA': total_ref,
            'Total_Predicted_GLC': total_pred,
            'Correct_Pixels': correct,
            'Producer_Accuracy (PA)': pa,
            'User_Accuracy (UA)': ua,
            'F1_Score': f1
        })

        # For aesthetics, add Overall Accuracy as a row at the bottom of the table
        oa_row = pd.DataFrame([{
            'Land_Cover_Class': 'OVERALL ACCURACY',
            'Total_Reference_ESA': total_samples,
            'Total_Predicted_GLC': total_samples,
            'Correct_Pixels': correct.sum(),
            'Producer_Accuracy (PA)': '-',
            'User_Accuracy (UA)': '-',
            'F1_Score': f"{oa:.4f}" # Use the F1 column to display the specific value of OA
        }])
        stats_df = pd.concat([stats_df, oa_row], ignore_index=True)

        # Export statistical report CSV
        stats_output_path = os.path.join(output_folder, f"{base_name}_accuracy_metrics.csv")
        stats_df.to_csv(stats_output_path, index=False)
        
        print(f"  ✅ Analysis complete: {base_name} (OA: {oa:.2%})")

print("\n🎉 All basin data statistics and confusion matrix images have been successfully generated!")