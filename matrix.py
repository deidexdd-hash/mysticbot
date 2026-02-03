from datetime import datetime


def split_digits(value):
    """Разделяет число на отдельные цифры"""
    return [int(x) for x in str(value).replace(".", "")]


def digit_sum(value):
    """Суммирует цифры числа до однозначного числа"""
    total = sum(split_digits(value))
    while total >= 10 and total not in [11, 22, 33]:
        total = sum(split_digits(total))
    return total


def calculate_matrix(date_str: str):
    """
    Расширенный расчет матрицы судьбы с дополнительными параметрами
    date_str формат: DD.MM.YYYY
    """
    date = datetime.strptime(date_str, "%d.%m.%Y")
    year = date.year
    month = date.month
    day = date.day
    
    # Разбиваем дату на цифры
    digits = split_digits(date.strftime("%d.%m.%Y"))
    
    # 1-е число (Характер) - сумма всех цифр даты
    first = sum(digits)
    
    # 2-е число (Душа) - сумма цифр первого числа
    second = digit_sum(first)
    
    # 3-е число (Судьба)
    if year >= 2000:
        third = first - 19
        extra = [1, 9]
    else:
        first_day_digit = digits[0] if digits[0] != 0 else digits[1]
        third = first - (first_day_digit * 2)
        extra = []
    
    # 4-е число (Кармическая задача) - сумма цифр третьего числа
    fourth = digit_sum(abs(third))
    
    # Полный массив цифр для анализа матрицы
    full_array = (
        digits
        + split_digits(first)
        + split_digits(second)
        + extra
        + split_digits(third)
        + split_digits(fourth)
    )
    
    # Дополнительные расчеты
    life_path_number = digit_sum(day + month + year)
    
    # Число выражения (полное имя)
    expression_number = digit_sum(sum(digits))
    
    # Число душевного пробуждения
    soul_urge_number = digit_sum(month + year)
    
    # Число личности
    personality_number = digit_sum(day + month)
    
    # Кармические долги
    karmic_debts = []
    for num in [13, 14, 16, 19]:
        if str(num) in ''.join(str(d) for d in full_array):
            karmic_debts.append(num)
    
    return {
        "date": date_str,
        "day": day,
        "month": month,
        "year": year,
        "digits": digits,
        "first": first,
        "second": second,
        "third": third,
        "fourth": fourth,
        "full": full_array,
        "life_path": life_path_number,
        "expression": expression_number,
        "soul_urge": soul_urge_number,
        "personality": personality_number,
        "karmic_debts": karmic_debts,
        "is_millennial": year >= 2000,
        "day_type": "основной" if day <= 9 else "расширенный",
    }


def analyze_compatibility(date1: str, date2: str):
    """
    Анализ совместимости двух матриц
    """
    matrix1 = calculate_matrix(date1)
    matrix2 = calculate_matrix(date2)
    
    compatibility_score = 0
    matches = []
    
    # Сравнение основных чисел
    if matrix1["second"] == matrix2["second"]:
        compatibility_score += 30
        matches.append("Души")
    
    if matrix1["life_path"] == matrix2["life_path"]:
        compatibility_score += 20
        matches.append("Жизненный путь")
    
    if matrix1["expression"] == matrix2["expression"]:
        compatibility_score += 15
        matches.append("Выражение")
    
    # Кармическая связь
    if any(num in matrix1["karmic_debts"] for num in matrix2["karmic_debts"]):
        compatibility_score += 10
        matches.append("Кармическая связь")
    
    return {
        "score": min(compatibility_score, 100),
        "matches": matches,
        "level": "высокая" if compatibility_score >= 50 else "средняя" if compatibility_score >= 30 else "низкая",
        "recommendation": "Гармоничный союз" if compatibility_score >= 50 else "Требует работы" if compatibility_score >= 30 else "Кармические уроки"
    }


def get_year_forecast(date_str: str, target_year: int = None):
    """
    Прогноз на год по матрице
    """
    matrix_data = calculate_matrix(date_str)
    
    if target_year is None:
        target_year = datetime.now().year
    
    personal_year = digit_sum(matrix_data["day"] + matrix_data["month"] + target_year)
    
    forecasts = {
        1: "Год новых начинаний, инициатив и независимости",
        2: "Год партнерства, сотрудничества и терпения",
        3: "Год творчества, самовыражения и радости",
        4: "Год труда, стабильности и построения основ",
        5: "Год перемен, свободы и приключений",
        6: "Год семьи, ответственности и гармонии",
        7: "Год анализа, духовности и уединения",
        8: "Год достижений, изобилия и власти",
        9: "Год завершений, мудрости и трансформации",
    }
    
    return {
        "personal_year": personal_year,
        "forecast": forecasts.get(personal_year, "Особый год"),
        "focus": "Действие" if personal_year in [1, 4, 7] else "Отношения" if personal_year in [2, 5, 8] else "Мудрость",
        "challenge": "Импульсивность" if personal_year in [1, 5] else "Пассивность" if personal_year in [2, 7] else "Излишняя эмоциональность"
    }
