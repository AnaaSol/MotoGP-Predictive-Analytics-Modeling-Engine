from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.core.database import Base

class Rider(Base):
    __tablename__ = "riders"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    bike_manufacturer = Column(String)  # e.g., "Ducati", "Aprilia"
    base_weight_kg = Column(Float)
    qrd_historical_avg = Column(Float, default=0.0)
    
    telemetry = relationship("LapTelemetry", back_populates="rider")

class Circuit(Base):
    __tablename__ = "circuits"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    length_km = Column(Float)
    total_laps = Column(Integer)
    heavy_braking_zones = Column(Integer) # For analyzing front tire wear

class RaceSession(Base):
    __tablename__ = "race_sessions"
    id = Column(Integer, primary_key=True, index=True)
    circuit_id = Column(Integer, ForeignKey("circuits.id"))
    session_type = Column(String) # e.g., "Qualifying", "Sprint", "Race"
    track_temp = Column(Float)
    air_temp = Column(Float)
    is_wet = Column(Boolean, default=False)
    date = Column(DateTime, server_default=func.now())

class LapTelemetry(Base):
    __tablename__ = "lap_telemetry"
    id = Column(Integer, primary_key=True, index=True)
    rider_id = Column(Integer, ForeignKey("riders.id"))
    session_id = Column(Integer, ForeignKey("race_sessions.id"))
    
    lap_number = Column(Integer)
    lap_time_raw = Column(Float)
    
    # Sector analysis for granular degradation
    s1_time = Column(Float)
    s2_time = Column(Float)
    s3_time = Column(Float)
    s4_time = Column(Float) # MotoGP tracks usually have 4 sectors
    
    # Tire specs for this specific stint
    front_compound = Column(String) # Soft, Medium, Hard
    rear_compound = Column(String)
    rear_tire_age_at_start = Column(Integer) # Laps already on tire
    
    # Engine/Fuel state
    fuel_load_est = Column(Float)
    engine_map = Column(String) # e.g., "Map 1", "Map 2"
    
    rider = relationship("Rider", back_populates="telemetry")