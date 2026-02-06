#%%
import pandas as pd
import pathlib
import re

def get_latest_file(folder_path, extension=".csv"):
    """
    Busca el archivo más reciente en una carpeta basándose en la fecha 
    del nombre (formato YYYY-MM-DD).
    """
    path = pathlib.Path(folder_path)
    # Buscamos archivos con la extensión deseada
    files = list(path.glob(f"*{extension}"))
    # Extraemos la fecha del nombre del archivo (asumiendo formato YYYY-MM-DD)
    # y ordenamos para obtener el último.
    def extract_date(file_path):
        match = re.search(r'(\d{4}-\d{2}-\d{2})', file_path.name)
        return match.group(1) if match else ""

    # Ordenamos por la fecha extraída y tomamos el último
    latest_file = max(files, key=extract_date)
    return latest_file

base_path = pathlib.Path.cwd() /".."/ "data"

# Cargamos los DataFrames usando la función
# Nota: Ajusta el delimitador si es necesario (tu ejemplo usa ';')
path_cabaprop = get_latest_file(base_path / "cabaprop")
cabaprop = pd.read_csv(path_cabaprop, sep=';') if path_cabaprop else None

path_zonaprop = get_latest_file(base_path / "zonaprop")
zonaprop = pd.read_csv(path_zonaprop, sep=';') if path_zonaprop else None

path_argenprop = get_latest_file(base_path / "argenprop")
argenprop = pd.read_csv(path_argenprop, sep=';') if path_argenprop else None
# %%
# 1. Unimos los dataframes (esto pone uno abajo del otro y alinea columnas por nombre)
departamentos = pd.concat([cabaprop, zonaprop, argenprop], ignore_index=True)

# 2. Reordenamos: Columnas comunes primero, luego el resto
columnas_comunes = [c for c in departamentos.columns if all(c in df.columns for df in [cabaprop, zonaprop, argenprop])]
otras_columnas = [c for c in departamentos.columns if c not in columnas_comunes]

departamentos = departamentos[columnas_comunes + otras_columnas]
# %%
departamentos
departamentos.dtypes
departamentos.isna().sum()
# %%
# 1. Lista de columnas numéricas
cols_num = ['Expensas', 'Ambientes', 'Dormitorios', 'Baños', 'Cocheras', 'Metros_Cubiertos', 'Metros_Totales', 'Visitas_Count']

for col in cols_num:
    if col in departamentos.columns:
        # Convertimos a numérico y usamos 'Int64' (con I mayúscula) 
        # Este tipo de dato de Pandas sí permite números enteros con valores nulos (NaN)
        departamentos[col] = pd.to_numeric(departamentos[col], errors='coerce').astype('Int64')

# 2. Conversión de fecha
# Usamos dayfirst=True porque tu archivo viene con formato DD/MM/YYYY
departamentos['Fecha_Publicacion'] = pd.to_datetime(departamentos['Fecha_Publicacion'], dayfirst=True, errors='coerce')
# %%
departamentos.to_excel(base_path / ".." / "data" / "departamentos.xlsx", index=False)
# %%
