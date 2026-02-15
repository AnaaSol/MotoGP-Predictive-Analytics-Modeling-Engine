# 🏁 MotoGP Predictive Analytics & Modeling Engine

An advanced Full-Stack and Machine Learning platform designed to decode the complexity of Grand Prix motorcycle racing. This project focuses on the "human-machine" interface, modeling high-variability factors like rider form, track temperature, and non-linear tire degradation.

---

## 🚀 Chosen Tech Stack

| Layer | Technology | Rationale |
| :--- | :--- | :--- |
| **Backend** | Python 3.12 / FastAPI | Asynchronous handling of telemetry streams. |
| **Database** | PostgreSQL / SQLAlchemy | Relational integrity for complex Rider/Track/Tire mappings. |
| **Migrations** | Alembic | Version-controlled schema evolution. |
| **ML/DL** | Scikit-learn, XGBoost, PyTorch | Hybrid approach (Gradient Boosting for winners, LSTMs for lap trends). |
| **Frontend** | React / TypeScript / Recharts | Type-safe, high-performance data visualization. |
| **Scraping** | Playwright / BeautifulSoup4 | Robust extraction from dynamic timing sites and PDF reports. |

---

## 📂 Repository Structure

```text
motogp-analytics/
├── alembic/                # Database migration environment
├── data/
│   ├── raw/                # Unprocessed JSON/HTML/PDF data
│   └── processed/          # Feature-engineered Parquet/CSV files
├── src/
│   ├── api/                # FastAPI routers and endpoints
│   ├── core/               # Database engine and global config
│   ├── models/             # SQLAlchemy ORM schemas
│   ├── ml_engine/          # Machine Learning pipelines
│   │   ├── features/       # Degradation & QRD logic
│   │   ├── training/       # Training & Hyperparameter scripts
│   │   └── inference/      # Model serving logic
│   └── scraper/            # Web scraping & ETL workers
├── web/                    # React + Tailwind + Vite frontend
├── docker-compose.yml      # Containerized PG and Redis
└── README.md
```

# 🧠 Architecture & Metrics

This section outlines the core mathematical and structural logic behind the MotoGP Predictive Engine.

---

### 1. Tire Degradation (The "Positive Slope")
MotoGP tires lose grip non-linearly. We calculate the **Degradation Coefficient ($\beta_1$)** by first normalizing lap times against fuel load depletion.

**Fuel-Adjusted Lap Time Formula:** $$L_{adj} = L_{raw} - (\alpha \cdot R_{rem})$$

* $L_{raw}$: Raw lap time.
* $\alpha$: Fuel sensitivity constant (seconds/liter).
* $R_{rem}$: Remaining fuel in the tank.

**Degradation Slope:** $$L_{adj} = \beta_{0} + \beta_{1} \cdot Lap_{n} + \epsilon$$

> **Note:** A high $\beta_1$ indicates "dropping off the cliff," a critical predictor for late-race overtaking and defensive vulnerability.



---

### 2. Quali-to-Race Conversion (QRD)
This metric identifies "Saturday Specialists" versus "Sunday Specialists" by measuring the delta between explosive speed and sustained pace.

$$\text{QRD Score} = \text{Avg. Race Pace Rank} - \text{Qualifying Rank}$$

* **Negative Score:** Indicates a rider who qualifies poorly but has superior race management (The "Sunday Man").
* **Positive Score:** Indicates a rider who can extract 1-lap speed but struggles with full-tank or worn-tire pace.

---

### 3. Track Temperature Normalization
Tire compound performance is modeled using a **Gaussian Heat Weighting**, prioritizing historical data where $T_{track}$ is within $\pm 5^\circ\text{C}$ of the predicted race start temperature.

---

## 🛠 Architectural Decisions

* **Relational Telemetry:** We utilize **PostgreSQL** for its robust indexing. Analyzing a rider's performance at *Turn 3 in Jerez* over 5 years requires the complex joining capabilities and transactional integrity of SQL.
* **Feature Priority (Recency Bias):** The model applies a decaying weight to historical data. A podium 2 years ago is weighted significantly less (approx. 80% reduction) than a Top 5 finish two weeks ago, accounting for the "volatile environment" of rider confidence and bike development.
* **Hybrid Modeling Approach:** * **XGBoost:** Used for the categorical "Winner/Podium" classification.
    * **LSTM (RNN):** Used for predicting the specific lap time of Lap 22 based on the sequential trends of Laps 1–21.

---

## 📈 Key Performance Indicators (KPIs)

* **Top 3 Hit Rate:** Percentage of predicted podiums that were correct.
* **Degradation MAE:** Mean Absolute Error in seconds for predicted lap times in the final 5 laps of the race.
* **Overtake Probability:** Logistic regression output on the likelihood of a position change based on the $\Delta$ in degradation between two riders in a trailing/leading scenario.
