from datetime import datetime


def split_digits(value):
    return [int(x) for x in str(value).replace(".", "")]


def digit_sum(value):
    return sum(split_digits(value))


def calculate_matrix(date_str: str):
    """
    Полностью повторяет логику App.tsx
    date_str формат: DD.MM.YYYY
    """

    date = datetime.strptime(date_str, "%d.%m.%Y")
    year = date.year

    # DD.MM.YYYY → цифры
    digits = split_digits(date.strftime("%d.%m.%Y"))

    # 1-е число
    first = sum(digits)

    # 2-е число
    second = digit_sum(first)

    # 3-е число
    if year >= 2000:
        third = first + 19
        extra = [1, 9]
    else:
        first_day_digit = digits[0] if digits[0] != 0 else digits[1]
        third = first - (first_day_digit * 2)
        extra = []

    # 4-е число
    fourth = digit_sum(abs(third))

    # fullArray как в App.tsx
    full_array = (
        digits
        + split_digits(first)
        + split_digits(second)
        + extra
        + split_digits(third)
        + split_digits(fourth)
    )

    return {
        "digits": digits,
        "first": first,
        "second": second,
        "third": third,
        "fourth": fourth,
        "full": full_array,
    }
