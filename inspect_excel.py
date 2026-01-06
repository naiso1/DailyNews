
import pandas as pd
import openpyxl

file_path = r'C:\Users\demo\Desktop\中村\DailyNews\search_results.xlsx'

try:
    # Load with openpyxl to check for hidden rows (filtering)
    wb = openpyxl.load_workbook(file_path)
    ws = wb.active
    
    print(f"Sheet Name: {ws.title}")
    
    total_rows = 0
    hidden_rows = 0
    visible_rows = 0
    
    # Iterate through rows to check visibility
    # Note: Row dimension hidden attribute
    for row in ws.iter_rows():
        if ws.row_dimensions[row[0].row].hidden:
            hidden_rows += 1
        else:
            visible_rows += 1
        total_rows += 1
            
    print(f"Total Rows (including header): {total_rows}")
    print(f"Visible Rows: {visible_rows}")
    print(f"Hidden Rows: {hidden_rows}")
    
    # Read with pandas to see columns
    df = pd.read_excel(file_path)
    print("\nColumns found:")
    for col in df.columns:
        print(f"- {col}")
        
    print("\nFirst 3 rows of data:")
    print(df.head(3).to_string())

except Exception as e:
    print(f"Error: {e}")
