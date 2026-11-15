
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "air_quality_hourly.csv"
PROC = ROOT / "data" / "processed"
FIG = ROOT / "figures"

# WHO Air Quality Guidelines 2021 (µg/m³)
WHO = {
    "no2_ugm3": {"annual": 10, "daily": 25},
    "pm25_ugm3": {"annual": 5, "daily": 15},
}
LABEL = {"no2_ugm3": "NO₂", "pm25_ugm3": "PM2.5"}
COLORS = {"STATION_TRAFFIC": "#c53030", "STATION_BACKGROUND": "#2b6cb0"}
NAMES = {"STATION_TRAFFIC": "Traffic", "STATION_BACKGROUND": "Background"}
POLLUTANTS = list(WHO)


def load() -> pd.DataFrame:
    df = pd.read_csv(RAW, parse_dates=["datetime"])
    # Interpolate short gaps (≤ 3 h) per station; longer gaps stay missing
    df[POLLUTANTS] = (
        df.groupby("station")[POLLUTANTS]
        .transform(lambda s: s.interpolate(limit=3, limit_area="inside"))
    )
    return df


def daily_means(df: pd.DataFrame) -> pd.DataFrame:
    """Daily means, valid only if ≥ 18 of 24 hours are available (75 % rule)."""
    g = df.set_index("datetime").groupby("station")[POLLUTANTS]
    mean = g.resample("D").mean()
    count = g.resample("D").count()
    return mean.where(count >= 18)


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)


def diurnal_cycle(df: pd.DataFrame) -> None:
    d = df.assign(hour=df.datetime.dt.hour,
                  daytype=df.datetime.dt.dayofweek.map(lambda x: "Weekend" if x >= 5 else "Weekday"))
    prof = d.groupby(["station", "daytype", "hour"])["no2_ugm3"].mean()

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, daytype in zip(axes, ["Weekday", "Weekend"]):
        for st, c in COLORS.items():
            ax.plot(prof.loc[st, daytype], color=c, lw=2, label=NAMES[st])
        ax.set_title(daytype)
        ax.set_xlabel("Hour of day")
        ax.set_xticks(range(0, 24, 3))
        style(ax)
    axes[0].set_ylabel("NO₂ (µg/m³)")
    axes[0].legend(frameon=False)
    fig.suptitle("Diurnal NO₂ cycle – traffic rush hours are visible on weekdays")
    fig.tight_layout()
    fig.savefig(FIG / "no2_diurnal_cycle.png", dpi=150)
    plt.close(fig)


def seasonal_cycle(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.reset_index()
    d["month"] = d.datetime.dt.month
    clim = d.groupby(["station", "month"])[POLLUTANTS].mean().round(1)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    months = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
    for ax, p in zip(axes, POLLUTANTS):
        for st, c in COLORS.items():
            ax.plot(clim.loc[st].index, clim.loc[st, p], color=c, marker="o", lw=2, label=NAMES[st])
        ax.axhline(WHO[p]["annual"], color="grey", ls="--", lw=1)
        ax.text(12.3, WHO[p]["annual"], "WHO\nannual", va="center", fontsize=8, color="grey")
        ax.set_title(LABEL[p])
        ax.set_ylabel("µg/m³")
        ax.set_xticks(range(1, 13), months)
        ax.set_ylim(bottom=0)
        style(ax)
    axes[0].legend(frameon=False)
    fig.suptitle("Monthly mean concentrations")
    fig.tight_layout()
    fig.savefig(FIG / "seasonal_cycle.png", dpi=150)
    plt.close(fig)
    return clim


def wind_effect(df: pd.DataFrame) -> pd.DataFrame:
    bins = [0, 1, 2, 3, 4, 5, 7, 20]
    labels = ["0–1", "1–2", "2–3", "3–4", "4–5", "5–7", ">7"]
    d = df.assign(wind_class=pd.cut(df.wind_ms, bins=bins, labels=labels))
    tab = d.groupby(["station", "wind_class"], observed=True)[POLLUTANTS].mean().round(1)

    fig, ax = plt.subplots(figsize=(7, 4))
    for st, c in COLORS.items():
        ax.plot(labels, tab.loc[st, "no2_ugm3"], color=c, marker="o", lw=2, label=f"{NAMES[st]} – NO₂")
        ax.plot(labels, tab.loc[st, "pm25_ugm3"], color=c, marker="s", lw=1.5, ls=":",
                label=f"{NAMES[st]} – PM2.5")
    ax.set_xlabel("Wind speed (m/s)")
    ax.set_ylabel("Mean concentration (µg/m³)")
    ax.set_title("Higher wind speeds dilute pollutants")
    ax.legend(frameon=False, fontsize=8)
    style(ax)
    fig.tight_layout()
    fig.savefig(FIG / "wind_effect.png", dpi=150)
    plt.close(fig)
    return tab


def who_exceedances(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.reset_index()
    d["year"] = d.datetime.dt.year
    rows = []
    for (st, yr), g in d.groupby(["station", "year"]):
        row = {"station": st, "year": yr}
        for p in POLLUTANTS:
            row[f"{p}_annual_mean"] = round(g[p].mean(), 1)
            row[f"{p}_days_above_who_daily"] = int((g[p] > WHO[p]["daily"]).sum())
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(exist_ok=True)

    df = load()
    daily = daily_means(df)

    diurnal_cycle(df)
    clim = seasonal_cycle(daily)
    wind = wind_effect(df)
    exc = who_exceedances(daily)

    clim.to_csv(PROC / "monthly_means.csv")
    wind.to_csv(PROC / "concentration_by_wind_class.csv")
    exc.to_csv(PROC / "who_exceedances.csv", index=False)

    corr = (df.groupby("station")[["no2_ugm3", "pm25_ugm3", "wind_ms", "temp_c"]]
              .corr(method="spearman").round(2))

    print("=== Annual means and WHO daily-guideline exceedance days ===")
    print(exc.to_string(index=False))
    print("\n=== Spearman correlations ===")
    print(corr)


if __name__ == "__main__":
    main()
