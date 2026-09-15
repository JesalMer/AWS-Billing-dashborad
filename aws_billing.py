import boto3
from datetime import date, timedelta


def get_ce_client(access_key, secret_key):

    return boto3.client(
        "ce",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1"
    )


def get_month_dates():

    today = date.today()

    current_start = today.replace(day=1)
    current_end = today + timedelta(days=1)

    if current_start.month == 1:

        previous_start = current_start.replace(
            year=current_start.year - 1,
            month=12,
            day=1
        )

    else:

        previous_start = current_start.replace(
            month=current_start.month - 1,
            day=1
        )

    return current_start, current_end, previous_start


def get_total_cost(client, start, end):

    response = client.get_cost_and_usage(

        TimePeriod={
            "Start": start.strftime("%Y-%m-%d"),
            "End": end.strftime("%Y-%m-%d")
        },

        Granularity="MONTHLY",

        Metrics=[
            "UnblendedCost"
        ]
    )

    total = 0

    for result in response.get("ResultsByTime", []):

        amount = result["Total"]["UnblendedCost"]["Amount"]

        total += float(amount)

    return round(total, 2)


def get_daily_cost(client, start, end):

    response = client.get_cost_and_usage(

        TimePeriod={
            "Start": start.strftime("%Y-%m-%d"),
            "End": end.strftime("%Y-%m-%d")
        },

        Granularity="DAILY",

        Metrics=[
            "UnblendedCost"
        ]
    )

    dates = []
    costs = []

    for result in response.get("ResultsByTime", []):

        dates.append(
            result["TimePeriod"]["Start"]
        )

        amount = result["Total"]["UnblendedCost"]["Amount"]

        costs.append(
            round(float(amount), 2)
        )

    return {
        "dates": dates,
        "costs": costs
    }


def get_service_cost(client, start, end):

    response = client.get_cost_and_usage(

        TimePeriod={
            "Start": start.strftime("%Y-%m-%d"),
            "End": end.strftime("%Y-%m-%d")
        },

        Granularity="MONTHLY",

        Metrics=[
            "UnblendedCost"
        ],

        GroupBy=[
            {
                "Type": "DIMENSION",
                "Key": "SERVICE"
            }
        ]
    )

    services = []

    for result in response.get("ResultsByTime", []):

        for group in result.get("Groups", []):

            service_name = group["Keys"][0]

            amount = group["Metrics"]["UnblendedCost"]["Amount"]

            cost = float(amount)

            if cost > 0:

                services.append({
                    "service": service_name,
                    "cost": round(cost, 2)
                })

    services.sort(
        key=lambda x: x["cost"],
        reverse=True
    )

    return services


def get_region_cost(client, start, end):

    response = client.get_cost_and_usage(

        TimePeriod={
            "Start": start.strftime("%Y-%m-%d"),
            "End": end.strftime("%Y-%m-%d")
        },

        Granularity="MONTHLY",

        Metrics=[
            "UnblendedCost"
        ],

        GroupBy=[
            {
                "Type": "DIMENSION",
                "Key": "REGION"
            }
        ]
    )

    regions = []

    for result in response.get("ResultsByTime", []):

        for group in result.get("Groups", []):

            region_name = group["Keys"][0]

            amount = group["Metrics"]["UnblendedCost"]["Amount"]

            cost = float(amount)

            if cost > 0:

                regions.append({
                    "region": region_name,
                    "cost": round(cost, 2)
                })

    regions.sort(
        key=lambda x: x["cost"],
        reverse=True
    )

    return regions


def get_billing_data(
    access_key,
    secret_key,
    region,
    start_date=None,
    end_date=None
):
    from datetime import datetime, timedelta

    client = get_ce_client(
        access_key,
        secret_key
    )

    today = date.today()
    show_forecast = True

    if start_date and end_date:
        if isinstance(start_date, str):
            current_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        else:
            current_start = start_date
        if isinstance(end_date, str):
            custom_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        else:
            custom_end = end_date
        
        current_end = custom_end + timedelta(days=1)
        
        # Accurate previous usage calculation (e.g. 15aug to 10sept -> previous usage = july + 1aug to 14aug)
        prev_year = current_start.year if current_start.month > 1 else current_start.year - 1
        prev_month = current_start.month - 1 if current_start.month > 1 else 12
        previous_start = date(prev_year, prev_month, 1)
        previous_end = current_start  # AWS CE End is exclusive, so it queries up to (current_start - 1 day)

        # Forecast is ONLY shown for current month! Never for past months or closed historical periods
        is_current_month = (current_start.year == today.year and current_start.month == today.month and custom_end >= today)
        if is_current_month:
            show_forecast = True
        else:
            show_forecast = False
            forecast = None
    else:
        current_start, current_end, previous_start = get_month_dates()
        previous_end = current_start
        show_forecast = True

    current_cost = get_total_cost(
        client,
        current_start,
        current_end
    )

    previous_cost = get_total_cost(
        client,
        previous_start,
        previous_end
    )

    daily = get_daily_cost(
        client,
        current_start,
        current_end
    )

    services = get_service_cost(
        client,
        current_start,
        current_end
    )

    regions = get_region_cost(
        client,
        current_start,
        current_end
    )

    tax = 0

    for item in services:
        if "tax" in item["service"].lower():
            tax += item["cost"]

    if show_forecast:
        days_elapsed = today.day
        if days_elapsed > 0:
            average_daily_cost = (
                current_cost / days_elapsed
            )

            if current_start.month == 12:
                next_month = current_start.replace(
                    year=current_start.year + 1,
                    month=1,
                    day=1
                )
            else:
                next_month = current_start.replace(
                    month=current_start.month + 1,
                    day=1
                )

            days_in_month = (
                next_month - current_start
            ).days

            forecast = (
                average_daily_cost *
                days_in_month
            )
        else:
            forecast = 0
    else:
        forecast = None

    return {
        "current_cost": round(
            current_cost,
            2
        ),

        "previous_cost": round(
            previous_cost,
            2
        ),

        "forecast": round(forecast, 2) if forecast is not None else None,
        "show_forecast": show_forecast,

        "tax": round(
            tax,
            2
        ),

        "daily": daily,

        "services": services,

        "regions": regions,

        "period": {
            "start": current_start.strftime("%Y-%m-%d"),
            "end": (current_end - timedelta(days=1)).strftime("%Y-%m-%d"),
            "days": (current_end - current_start).days,
            "previous_start": previous_start.strftime("%Y-%m-%d"),
            "previous_end": (previous_end - timedelta(days=1)).strftime("%Y-%m-%d")
        }
    }
