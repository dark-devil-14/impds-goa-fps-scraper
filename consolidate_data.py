# Consolidate all the data from the different sources into a single DataFrame and save it to a CSV file

import json
import os
import pandas as pd


folder_path = "data\\raw" # for locating diffrent folders 
loop_path = ["2026-03//north_goa", "2026-03//south_goa", "2026-04//north_goa", "2026-04//south_goa"] # list of folders to loop through
# load the multiple data one by one and consolidate them into a single DataFrame
dataframes = []
for path in loop_path:
    file_path = os.path.join(folder_path, path) # joins the folder path and the loop path to get the full path of the folder
    for filename in os.listdir(file_path): # loop through the files in the folder (different fps)
        if filename.endswith(".json"): # checks if file is json return true
            with open(os.path.join(file_path, filename), "r") as f:
                data = json.load(f) # loads each fps file in data one by one
                # basic details 
                basic_detail = {
                    "year": data["year"],
                    "month": data["month"],
                    "state": data["state"],
                    "district": data["district"],
                    "fps_id": data["fps_id"],
                    "fps_name": data["fps_name"],
                }

                # summary cards
                for k, v in data["summary_cards"].items():
                    basic_detail[f"summary_{k}"] = v

                # transaction (PHH AND AAY)
                for item in data["number_of_transactions"]:
                    prefix_Keyword = "txn_phh" if "PHH" in item["row_label"] else "txn_aay"
                    for k, v in item.items():
                        if k != "row_label":
                            basic_detail[f"{prefix_Keyword}_{k}"] = v

                # for ration card(rc)  ( PHH AND AAT)
                for item in data["number_of_transacted_ration_cards"]:
                    prefix_Keyword = "rc_phh" if "PHH" in item["row_label"] else "rc_aay"
                    for k, v in item.items():
                        if k != "row_label":
                            basic_detail[f"{prefix_Keyword}_{k}"] = v

                # for distributed quantity (dty)
                for item in data["distributed_quantity_kg"]:
                    label = item["row_label"].lower().replace(" ", "_")
                    basic_detail[f"dty_{label}_regular"] = item["regular"]
                    basic_detail[f"dty_{label}_intra_state"] = item["intra_state"]
                    basic_detail[f"dty_{label}_inter_state"] = item["inter_state"]
                    basic_detail[f"dty_{label}_total"] = item["total"]

                df =pd.DataFrame([basic_detail])
                dataframes.append(df)
consolidated_df = pd.concat(dataframes, ignore_index=True)

# save as csv file 
consolidated_df.to_csv("data/processed/consolidated_fps_data.csv", index=False)
