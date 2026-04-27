import io
import matplotlib.pyplot as plt
from decimal import Decimal

def generar_grafico_resumen(ingresos: Decimal, gastos: Decimal, comision: Decimal, neto: Decimal) -> io.BytesIO:
    """
    Genera un gráfico de barras con el resumen financiero.
    Devuelve un buffer de bytes con la imagen en formato PNG.
    """
    labels = ['Ingresos', 'Gastos', 'Comisión', 'Neto']
    valores = [float(ingresos), float(gastos), float(comision), float(neto)]
    
    # Colores: Azul, Rojo, Naranja, Verde (o Rojo si el neto es negativo)
    color_neto = '#4CAF50' if neto >= 0 else '#d32f2f'
    colors = ['#2196F3', '#f44336', '#ff9800', color_neto]

    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(labels, valores, color=colors)

    # Añadir los valores en texto sobre (o debajo de) cada barra
    ax.bar_label(bars, fmt='$%g', padding=3, fontweight='bold')

    # Estilos del gráfico
    ax.set_title('Resumen Financiero', fontsize=14, fontweight='bold', pad=15)
    ax.set_ylabel('Monto (RD$)', fontsize=12)
    ax.grid(axis='y', linestyle='--', alpha=0.7)
    
    # Línea negra sólida en el 0 (útil si hay números negativos)
    ax.axhline(0, color='black', linewidth=1)
    
    # Ajustar márgenes superior/inferior para que los textos no se corten
    max_val = max(max(valores), 0)
    min_val = min(min(valores), 0)
    ax.set_ylim(min_val * 1.2, max_val * 1.2 if max_val > 0 else 100)

    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight')
    plt.close(fig)
    buffer.seek(0)
    
    return buffer