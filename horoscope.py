from datetime import datetime
from values import matrix, tasks


def get_matrix_value(full_array, number: int) -> str:
    """
    Абсолютно идентично getMatrixValue из App.tsx
    """
    count = full_array.count(number)

    if count == 0:
        key = f"{number}0"
    elif count > 5:
        key = str(number) * (count - 5)
    else:
        key = str(number) * count

    return matrix.get(key, "—")


def build_matrix_text(matrix_data):
    full = matrix_data["full"]

    text = "🔢 *Матрица судьбы*\n\n"
    for n in range(1, 10):
        text += f"*{n}:*\n{get_matrix_value(full, n)}\n\n"

    return text


def build_tasks_text(matrix_data):
    soul_task = tasks.get(str(matrix_data["second"]), "")
    clan_task = tasks.get(str(matrix_data["fourth"]), "")

    text = "🧬 *Кармические задачи*\n\n"
    if soul_task:
        text += f"*Личная задача Души:*\n{soul_task}\n\n"
    if clan_task:
        text += f"*Родовая задача (ЧРП):*\n{clan_task}\n\n"

    return text


def daily_horoscope(matrix_data):
    today = datetime.now().strftime("%d.%m.%Y")

    return f"""
✨ *Гороскоп на {today}*

Энергия дня формируется через твою психоматрицу.
Сегодня важно не идти против своей природы.

*Фокус дня:* {matrix_data["second"]}
*Кармическая проверка:* {matrix_data["fourth"]}

Совет:
Действуй осознанно. Любое сопротивление сегодня бьёт по энергии.
"""
