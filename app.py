import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from pathlib import Path


DEFAULT_GTFS_PATH = "google_transit_31_03_2026"
TRINDADE_STOP_ID = 5726
DESTINO = "Aeroporto"

st.set_page_config(
    page_title="Próximas partidas para o Aeroporto",
    page_icon="🚇",
    layout="centered"
)


@st.cache_data
def load_gtfs_data(gtfs_path: str):
    gtfs_path = Path(gtfs_path)

    stop_times = pd.read_csv(gtfs_path / "stop_times.txt")
    trips = pd.read_csv(gtfs_path / "trips.txt")
    calendar_dates = pd.read_csv(gtfs_path / "calendar_dates.txt")

    stop_times["stop_id"] = stop_times["stop_id"].astype(int)
    stop_times["stop_sequence"] = stop_times["stop_sequence"].astype(int)

    calendar_dates["date"] = pd.to_datetime(
        calendar_dates["date"],
        format="%Y%m%d"
    ).dt.date

    return stop_times, trips, calendar_dates


def get_operational_day(now: datetime) -> datetime:
    """
    Em operação GTFS, horários após a meia-noite podem pertencer ao dia anterior.
    Exemplo: 25:07:00 corresponde a 01:07 do dia seguinte.
    """
    if now.hour < 2:
        return now - timedelta(days=1)

    return now


def get_day_suffix(day: datetime) -> str:
    weekday = day.isoweekday()

    if 1 <= weekday <= 5:
        return "U"

    if weekday == 6:
        return "S"

    return "DF"


def convert_gtfs_time_to_datetime(gtfs_time: str, operational_day: datetime) -> datetime:
    hours, minutes, seconds = map(int, gtfs_time.split(":"))

    return datetime(
        operational_day.year,
        operational_day.month,
        operational_day.day
    ) + timedelta(hours=hours, minutes=minutes, seconds=seconds)


def get_trips_starting_at_stop(stop_times: pd.DataFrame, stop_id: int) -> list:
    first_stops = (
        stop_times
        .sort_values(["trip_id", "stop_sequence"])
        .groupby("trip_id")
        .first()
        .reset_index()
    )

    return first_stops[first_stops["stop_id"] == stop_id]["trip_id"].tolist()


def prepare_airport_trips(
    stop_times: pd.DataFrame,
    trips: pd.DataFrame,
    calendar_dates: pd.DataFrame,
    stop_id: int,
    destination: str,
    now: datetime
) -> pd.DataFrame:

    operational_day = get_operational_day(now)
    day_suffix = get_day_suffix(operational_day)

    trindade_origin_trips = get_trips_starting_at_stop(stop_times, stop_id)

    df = stop_times.merge(
        trips[["trip_id", "service_id", "trip_headsign"]],
        on="trip_id",
        how="left"
    )

    airport_trips = df[
        (df["trip_headsign"] == destination) &
        (df["stop_id"] == stop_id)
    ].copy()

    today_calendar = calendar_dates[
        calendar_dates["date"] == operational_day.date()
    ]

    if not today_calendar.empty:
        airport_trips = airport_trips.merge(
            today_calendar[["service_id", "exception_type"]],
            on="service_id",
            how="left"
        )

        valid_trips = airport_trips[
            (airport_trips["exception_type"] != 2) &
            (
                airport_trips["service_id"].str.endswith(day_suffix) |
                (airport_trips["exception_type"] == 1)
            )
        ].copy()
    else:
        valid_trips = airport_trips[
            airport_trips["service_id"].str.endswith(day_suffix)
        ].copy()

    valid_trips["actual_arrival_time"] = valid_trips["arrival_time"].apply(
        lambda value: convert_gtfs_time_to_datetime(value, operational_day)
    )

    valid_trips["platform"] = valid_trips["trip_id"].apply(
        lambda trip_id: "3" if trip_id in trindade_origin_trips else "1"
    )

    return valid_trips


def get_next_arrivals(valid_trips: pd.DataFrame, now: datetime, limit: int = 5):
    return (
        valid_trips[valid_trips["actual_arrival_time"] > now]
        .sort_values("actual_arrival_time")
        .head(limit)
    )

@st.fragment(run_every=1)
def countdown(timer):
    now = datetime.now()

    if timer > now:
        delta = timer - now
        seconds = int(delta.total_seconds())

        if seconds <= 120:
            formatted_delta = f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"

            if seconds <= 30:
                color = "red"
                blink_css = """
                <style>
                @keyframes blink {
                    0% { opacity: 1; }
                    30% { opacity: 0; }
                    50% { opacity: 1; }
                    80% { opacity: 0; }
                    100% { opacity: 1; }
                }
                </style>
                """
                animation = "animation: blink 1s infinite;"
            elif seconds <= 60:
                color = "orange"
                blink_css = ""
                animation = ""
            else:
                color = "default"
                blink_css = ""
                animation = ""
            st.write("Tempo restante")
            st.html(f"""
                {blink_css}
                <div style="
                    color: {color};
                    font-size: 81px;
                    {animation}
                ">
                    {formatted_delta}
                </div>
            """)
        else:
            dias = f"{delta.days} dia{'s' if delta.days != 1 else ''},"
            horas = f"{delta.seconds // 3600} hora{'s' if delta.seconds // 3600 != 1 else ''} e"
            minutos = (delta.seconds % 3600) // 60
            st.metric(
                "Tempo restante",
                f"{dias if dias != '0 dias,' else ''} {horas if horas != '0 horas e' else ''} {minutos:02d} minutos"
            )

#st.title("🚇 Próximas partidas para o Aeroporto")
gtfs_path = DEFAULT_GTFS_PATH
number_of_results = 5

try:
    stop_times, trips, calendar_dates = load_gtfs_data(gtfs_path)

    now = datetime.now()

    valid_trips = prepare_airport_trips(
        stop_times=stop_times,
        trips=trips,
        calendar_dates=calendar_dates,
        stop_id=TRINDADE_STOP_ID,
        destination=DESTINO,
        now=now
    )

    next_arrivals = get_next_arrivals(
        valid_trips=valid_trips,
        now=now,
        limit=number_of_results
    )

    #st.metric("Hora atual", now.strftime("%H:%M:%S"))

    if next_arrivals.empty:
        st.warning("Não foram encontradas próximas partidas para o Aeroporto.")
    else:
        first = next_arrivals.iloc[0]
        st.subheader(f"Próxima partida para o Aeroporto")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Cais", first["platform"])
        with col2:
            st.metric("Hora", first["arrival_time"])
        countdown(first["actual_arrival_time"])
        if len(next_arrivals) > 1:
            second = next_arrivals.iloc[1]
            st.info(
                f"A partida seguinte é às **{second['arrival_time']}**, "
                f"no Cais **{second['platform']}**."
            )

        display_df = next_arrivals[
            [
                "actual_arrival_time",
                "platform",
                "trip_headsign"
            ]
        ].copy()

        display_df["actual_arrival_time"] = display_df[
            "actual_arrival_time"
        ].dt.strftime("%H:%M:%S")

        display_df = display_df.rename(columns={
            "actual_arrival_time": "Horário",
            "platform": "Cais",
            "trip_headsign": "Destino"
        })

        st.subheader("Próximas partidas")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

except FileNotFoundError as error:
    st.error(f"Ficheiro não encontrado: {error}")

except Exception as error:
    st.error(f"Ocorreu um erro ao processar os dados: {error}")