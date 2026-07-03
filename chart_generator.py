import io
import matplotlib
matplotlib.use('Agg') # Uso en servidores sin GUI (Railway/Linux)
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from decimal import Decimal

def _crear_grafico_financiero(titulo: str, subtitulo: str, ingresos: Decimal, gastos: Decimal, comision: Decimal, neto: Decimal) -> io.BytesIO:
    """
    Función base interna para renderizar un gráfico financiero premium tipo FinTech.
    """
    labels = ['Ingresos\nTotales', 'Gastos\nOperativos', 'Comisión\nAdministrativa', 'Neto a\nEntregar']
    valores = [float(ingresos), float(gastos), float(comision), float(neto)]
    
    # Paleta FinTech moderna (Emerald, Rose, Amber, Indigo/Crimson según neto)
    color_neto = '#4F46E5' if neto >= 0 else '#E11D48'
    colors = ['#10B981', '#F43F5E', '#F59E0B', color_neto]
    edge_colors = ['#059669', '#E11D48', '#D97706', '#4338CA' if neto >= 0 else '#BE123C']

    fig, ax = plt.subplots(figsize=(8, 5.5), dpi=200)
    fig.patch.set_facecolor('#F8FAFC')
    ax.set_facecolor('#FFFFFF')

    # Rejilla trasera sutil
    ax.grid(axis='y', linestyle='--', color='#F1F5F9', linewidth=1.2, zorder=0)

    bars = ax.bar(labels, valores, color=colors, edgecolor=edge_colors, linewidth=1.5, width=0.52, zorder=3)

    # Eliminar bordes (spines) superior, derecho e izquierdo para estética limpia
    for spine in ['top', 'right', 'left']:
        ax.spines[spine].set_visible(False)
    ax.spines['bottom'].set_color('#CBD5E1')
    ax.spines['bottom'].set_linewidth(1.5)

    # Formatear etiquetas en barras
    for bar in bars:
        height = bar.get_height()
        offset = height * 0.02 if height >= 0 else height * 0.05
        formatted_val = f"RD$ {height:,.2f}" if abs(height) >= 1 else "$0.00"
        ax.annotate(formatted_val,
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 6 if height >= 0 else -16),  
                    textcoords="offset points",
                    ha='center', va='bottom' if height >= 0 else 'top',
                    fontsize=9.5, fontweight='bold', color='#1E293B')

    # Títulos y subtítulos
    ax.set_title(titulo, fontsize=15, fontweight='bold', color='#0F172A', pad=25)
    fig.text(0.5, 0.90, subtitulo, ha='center', fontsize=10.5, color='#64748B', fontweight='medium')
    fig.text(0.5, 0.02, "Alqui_bot • Gestión Inteligente y Control Financiero", ha='center', fontsize=8.5, color='#94A3B8', style='italic')

    # Formatear eje Y
    ax.yaxis.set_major_formatter(ticker.StrMethodFormatter('RD$ {x:,.0f}'))
    ax.tick_params(axis='y', colors='#64748B', labelsize=8.5)
    ax.tick_params(axis='x', colors='#334155', labelsize=10, length=0)

    # Ajustar límites Y para que las anotaciones no se corten
    max_val = max(max(valores), 0)
    min_val = min(min(valores), 0)
    rango = (max_val - min_val) if (max_val - min_val) > 0 else 1000
    ax.set_ylim(min_val - (rango * 0.15), max_val + (rango * 0.18))

    # Línea en cero si hay negativos o para sentar base
    ax.axhline(0, color='#94A3B8', linewidth=1.2, zorder=2)

    plt.tight_layout(rect=[0, 0.04, 1, 0.88])

    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buffer.seek(0)
    return buffer

def generar_grafico_resumen(ingresos: Decimal, gastos: Decimal, comision: Decimal, neto: Decimal) -> io.BytesIO:
    """Genera un gráfico de barras premium con el resumen financiero general."""
    return _crear_grafico_financiero(
        titulo="ESTADO FINANCIERO GENERAL",
        subtitulo="Balance acumulado de ingresos, gastos y margen neto",
        ingresos=ingresos, gastos=gastos, comision=comision, neto=neto
    )

def generar_grafico_mensual(mes: int, anio: int, ingresos: Decimal, gastos: Decimal, comision: Decimal, neto: Decimal) -> io.BytesIO:
    """Genera un gráfico de barras premium específico para un mes y año."""
    meses = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    nombre_mes = meses[mes] if 1 <= mes <= 12 else f"Mes {mes}"
    return _crear_grafico_financiero(
        titulo=f"BALANCE DEL MES • {nombre_mes.upper()} {anio}",
        subtitulo=f"Desglose de rendimiento financiero en {nombre_mes} {anio}",
        ingresos=ingresos, gastos=gastos, comision=comision, neto=neto
    )