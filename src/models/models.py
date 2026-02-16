from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.core.database_base import Base

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
    
    rider = relationship("Rider", back_populates="telemetry")
    
    lap_number = Column(Integer)
    lap_time_raw = Column(Float)
    
    # This will now link to as many sectors as the track provides
    sectors = relationship("LapSector", back_populates="lap")
    
    front_compound = Column(String)
    rear_compound = Column(String)
    fuel_load_est = Column(Float)

class LapSector(Base):
    __tablename__ = "lap_sectors"
    id = Column(Integer, primary_key=True, index=True)
    lap_id = Column(Integer, ForeignKey("lap_telemetry.id"))
    
    sector_number = Column(Integer) 
    sector_time = Column(Float)
    
    lap = relationship("LapTelemetry", back_populates="sectors")