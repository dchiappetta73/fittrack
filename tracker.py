import streamlit as st
import pandas as pd
from datetime import date, timedelta
import plotly.express as px
from supabase import create_client, Client

st.set_page_config(page_title="4-Day Upper/Lower Recomp Tracker", layout="wide")

# ---------------------------
# Supabase connection
# ---------------------------
@st.cache_resource
def init_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# ---------------------------
# Data helpers
# ---------------------------
def load_workouts():
    response = supabase.table("workouts").select("*").order("Date").execute()
    data = response.data if response.data else []
    return pd.DataFrame(data)

def load_nutrition():
    response = supabase.table("nutrition").select("*").order("Date").execute()
    data = response.data if response.data else []
    return pd.DataFrame(data)

def insert_workout(row):
    payload = {
        "Date": str(row["Date"]),
        "Week": int(row["Week"]),
        "Stage": row["Stage"],
        "Day": row["Day"],
        "Bodyweight": float(row["Bodyweight"]),
        "Primary_Exercise": row["Primary Exercise"],
        "Selected_Exercise": row["Selected Exercise"],
        "Category": row["Category"],
        "Sets": float(row["Sets"]),
        "Reps": float(row["Reps"]),
        "Load": float(row["Load"]),
        "RPE": float(row["RPE"]),
        "Notes": row["Notes"]
    }
    supabase.table("workouts").insert(payload).execute()

def insert_nutrition(row):
    payload = {
        "Date": str(row["Date"]),
        "Week": int(row["Week"]),
        "Bodyweight": float(row["Bodyweight"]),
        "Calories": float(row["Calories"]),
        "Protein": float(row["Protein"]),
        "Carbs": float(row["Carbs"]),
        "Fat": float(row["Fat"]),
        "Target_Calories": float(row["Target Calories"]),
        "Target_Protein": float(row["Target Protein"]),
        "Target_Carbs": float(row["Target Carbs"]),
        "Target_Fat": float(row["Target Fat"])
    }
    supabase.table("nutrition").insert(payload).execute()

# ---------------------------
# Helpers
# ---------------------------
def get_stage(week):
    if week <= 4:
        return "Foundation", "🟢 Foundation (Weeks 1-4)"
    elif week <= 8:
        return "Build", "🟡 Build (Weeks 5-8)"
    return "Peak", "🔴 Peak (Weeks 9-12)"

def get_latest_logged_weight(default_weight, workouts_df, nutrition_df):
    latest_weight = float(default_weight)

    if not nutrition_df.empty and "Bodyweight" in nutrition_df.columns:
        nut_df = nutrition_df.copy()
        nut_df["Date"] = pd.to_datetime(nut_df["Date"], errors="coerce")
        nut_df["Bodyweight"] = pd.to_numeric(nut_df["Bodyweight"], errors="coerce")
        nut_df = nut_df.dropna(subset=["Date", "Bodyweight"]).sort_values("Date")
        if not nut_df.empty:
            latest_weight = float(nut_df.iloc[-1]["Bodyweight"])

    if not workouts_df.empty and "Bodyweight" in workouts_df.columns:
        wk_df = workouts_df.copy()
        wk_df["Date"] = pd.to_datetime(wk_df["Date"], errors="coerce")
        wk_df["Bodyweight"] = pd.to_numeric(wk_df["Bodyweight"], errors="coerce")
        wk_df = wk_df.dropna(subset=["Date", "Bodyweight"]).sort_values("Date")
        if not wk_df.empty:
            latest_weight = float(wk_df.iloc[-1]["Bodyweight"])

    return latest_weight

def calculate_macros(bodyweight_lbs, height_inches, age, gender, activity_level, training_experience, goal):
    weight_kg = bodyweight_lbs * 0.453592
    height_cm = height_inches * 2.54

    if gender == "Male":
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5
    else:
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161

    activity_map = {
        "Sedentary": 1.2,
        "Lightly Active": 1.375,
        "Moderately Active": 1.55,
        "Very Active": 1.725,
        "Extremely Active": 1.9
    }
    tdee = bmr * activity_map[activity_level]

    if training_experience == "Beginner":
        recomp_adj, cut_adj, bulk_adj, protein_g_per_kg = -150, -350, 150, 1.8
    elif training_experience == "Intermediate":
        recomp_adj, cut_adj, bulk_adj, protein_g_per_kg = -200, -450, 200, 2.0
    else:
        recomp_adj, cut_adj, bulk_adj, protein_g_per_kg = -250, -500, 250, 2.2

    if age >= 50:
        protein_g_per_kg = max(protein_g_per_kg, 2.0)

    if goal == "Recomp":
        target_calories = tdee + recomp_adj
    elif goal == "Cut":
        target_calories = tdee + cut_adj
    else:
        target_calories = tdee + bulk_adj

    fat_g_per_kg = 0.7 if goal == "Cut" else 0.9 if goal == "Bulk" else 0.8
    target_protein = weight_kg * protein_g_per_kg
    target_fat = weight_kg * fat_g_per_kg
    target_carbs = max((target_calories - ((target_protein * 4) + (target_fat * 9))) / 4, 0)

    return {
        "bmr": int(round(bmr)),
        "tdee": int(round(tdee)),
        "calories": int(round(target_calories)),
        "protein": int(round(target_protein)),
        "carbs": int(round(target_carbs)),
        "fat": int(round(target_fat))
    }

def calculate_weekly_set_targets(goal, training_experience):
    if training_experience == "Beginner":
        base = {
            "Chest": (8, 12), "Back": (8, 12), "Delts": (6, 10), "Rear Delts": (4, 8),
            "Biceps": (4, 8), "Triceps": (4, 8), "Quads": (8, 12), "Hamstrings": (8, 12),
            "Calves": (4, 8), "Core": (4, 8)
        }
    elif training_experience == "Intermediate":
        base = {
            "Chest": (10, 16), "Back": (10, 16), "Delts": (8, 14), "Rear Delts": (4, 10),
            "Biceps": (5, 10), "Triceps": (5, 10), "Quads": (10, 16), "Hamstrings": (10, 16),
            "Calves": (5, 10), "Core": (4, 8)
        }
    else:
        base = {
            "Chest": (12, 18), "Back": (12, 18), "Delts": (10, 16), "Rear Delts": (6, 12),
            "Biceps": (6, 12), "Triceps": (6, 12), "Quads": (12, 18), "Hamstrings": (12, 18),
            "Calves": (6, 12), "Core": (6, 10)
        }

    if goal == "Cut":
        adjusted = {}
        for k, v in base.items():
            adjusted[k] = (max(v[0] - 2, 4), max(v[1] - 2, 6))
        return adjusted
    return base

def build_program():
    return {
        "Upper 1": {
            "Foundation": {
                "warmup": [
                    "5 min bike or elliptical",
                    "Foam roll T-spine x 45-60 sec",
                    "Quadruped T-spine rotation x 8/side",
                    "Wall slides x 10",
                    "Band pull-aparts x 15",
                    "Band external rotation x 12/side",
                    "Scap push-up x 8",
                    "Dead bug x 8/side",
                    "2-3 ramp-up sets for first press and first row"
                ],
                "primary": [
                    {"exercise": "Machine Chest Press", "category": "Chest", "sets": 3, "reps": 10, "subs": ["DB Floor Press", "Cable Press", "Push-up"]},
                    {"exercise": "Seated Row", "category": "Back", "sets": 3, "reps": 10, "subs": ["Chest-Supported Row", "Cable Row", "Machine Row"]},
                    {"exercise": "Lat Pulldown", "category": "Back", "sets": 3, "reps": 10, "subs": ["High Row", "Assisted Pull-up"]},
                    {"exercise": "Machine Shoulder Press", "category": "Delts", "sets": 2, "reps": 10, "subs": ["Landmine Press", "Incline Press (light)"]},
                    {"exercise": "Face Pull", "category": "Rear Delts", "sets": 2, "reps": 15, "subs": ["Rear Delt Fly", "Band Pull-Apart"]},
                    {"exercise": "DB Curl", "category": "Biceps", "sets": 2, "reps": 12, "subs": ["Hammer Curl", "Cable Curl"]},
                    {"exercise": "Cable Pressdown", "category": "Triceps", "sets": 2, "reps": 12, "subs": ["Overhead Rope Extension", "Bench Dip (assisted)"]}
                ]
            },
            "Build": {
                "warmup": [
                    "5 min bike or elliptical",
                    "Foam roll T-spine x 45-60 sec",
                    "Quadruped T-spine rotation x 10/side",
                    "Wall slides x 10",
                    "Band pull-aparts x 20",
                    "Band external rotation x 15/side",
                    "Scap push-up x 10",
                    "Dead bug x 10/side",
                    "2-3 ramp-up sets for first press and first row"
                ],
                "primary": [
                    {"exercise": "Machine Chest Press", "category": "Chest", "sets": 4, "reps": 8, "subs": ["DB Floor Press", "Cable Press", "Push-up"]},
                    {"exercise": "Seated Row", "category": "Back", "sets": 4, "reps": 8, "subs": ["Chest-Supported Row", "Cable Row", "Machine Row"]},
                    {"exercise": "Lat Pulldown", "category": "Back", "sets": 4, "reps": 8, "subs": ["High Row", "Assisted Pull-up"]},
                    {"exercise": "Machine Shoulder Press", "category": "Delts", "sets": 3, "reps": 8, "subs": ["Landmine Press", "Incline Press (light)"]},
                    {"exercise": "Face Pull", "category": "Rear Delts", "sets": 3, "reps": 12, "subs": ["Rear Delt Fly", "Band Pull-Apart"]},
                    {"exercise": "DB Curl", "category": "Biceps", "sets": 3, "reps": 10, "subs": ["Hammer Curl", "Cable Curl"]},
                    {"exercise": "Cable Pressdown", "category": "Triceps", "sets": 3, "reps": 10, "subs": ["Overhead Rope Extension", "Bench Dip (assisted)"]}
                ]
            },
            "Peak": {
                "warmup": [
                    "5 min bike or elliptical",
                    "Foam roll T-spine x 60 sec",
                    "Quadruped T-spine rotation x 10/side",
                    "Wall slides x 12",
                    "Band pull-aparts x 20",
                    "Band external rotation x 15/side",
                    "Scap push-up x 10",
                    "Dead bug x 10/side",
                    "2-4 ramp-up sets for first press and first row"
                ],
                "primary": [
                    {"exercise": "Machine Chest Press", "category": "Chest", "sets": 4, "reps": 6, "subs": ["DB Floor Press", "Cable Press", "Push-up"]},
                    {"exercise": "Seated Row", "category": "Back", "sets": 4, "reps": 6, "subs": ["Chest-Supported Row", "Cable Row", "Machine Row"]},
                    {"exercise": "Lat Pulldown", "category": "Back", "sets": 4, "reps": 8, "subs": ["High Row", "Assisted Pull-up"]},
                    {"exercise": "Machine Shoulder Press", "category": "Delts", "sets": 3, "reps": 8, "subs": ["Landmine Press", "Incline Press (light)"]},
                    {"exercise": "Face Pull", "category": "Rear Delts", "sets": 3, "reps": 12, "subs": ["Rear Delt Fly", "Band Pull-Apart"]},
                    {"exercise": "DB Curl", "category": "Biceps", "sets": 3, "reps": 10, "subs": ["Hammer Curl", "Cable Curl"]},
                    {"exercise": "Cable Pressdown", "category": "Triceps", "sets": 3, "reps": 10, "subs": ["Overhead Rope Extension", "Bench Dip (assisted)"]}
                ]
            }
        },
        "Lower 1": {
            "Foundation": {
                "warmup": [
                    "5 min bike",
                    "Cat-cow x 8",
                    "Quadruped rock-back x 10",
                    "Glute bridge x 10",
                    "Bird dog x 8/side",
                    "Hip flexor mobilization x 8/side",
                    "Ankle rocks x 10/side",
                    "Bodyweight squat x 10",
                    "2-4 ramp-up sets for first lower-body movement"
                ],
                "primary": [
                    {"exercise": "Leg Press", "category": "Quads", "sets": 4, "reps": 10, "subs": ["Goblet Squat", "Hack Squat Machine", "Box Squat"]},
                    {"exercise": "Hamstring Curl", "category": "Hamstrings", "sets": 3, "reps": 12, "subs": ["Stability Ball Curl", "Glute Bridge"]},
                    {"exercise": "Split Squat", "category": "Quads", "sets": 3, "reps": 10, "subs": ["Step-up", "Reverse Lunge"]},
                    {"exercise": "Calf Raise", "category": "Calves", "sets": 3, "reps": 15, "subs": ["Seated Calf Raise", "Single-Leg Calf Raise"]},
                    {"exercise": "Bird Dog", "category": "Core", "sets": 2, "reps": 10, "subs": ["Dead Bug", "Pallof Press"]}
                ]
            },
            "Build": {
                "warmup": [
                    "5 min bike",
                    "Cat-cow x 8",
                    "Quadruped rock-back x 10",
                    "Glute bridge x 12",
                    "Bird dog x 10/side",
                    "Hip flexor mobilization x 10/side",
                    "Ankle rocks x 10/side",
                    "Bodyweight squat x 10",
                    "2-4 ramp-up sets for first lower-body movement"
                ],
                "primary": [
                    {"exercise": "Leg Press", "category": "Quads", "sets": 4, "reps": 8, "subs": ["Goblet Squat", "Hack Squat Machine", "Box Squat"]},
                    {"exercise": "Hamstring Curl", "category": "Hamstrings", "sets": 4, "reps": 10, "subs": ["Stability Ball Curl", "Glute Bridge"]},
                    {"exercise": "Split Squat", "category": "Quads", "sets": 3, "reps": 8, "subs": ["Step-up", "Reverse Lunge"]},
                    {"exercise": "Calf Raise", "category": "Calves", "sets": 4, "reps": 12, "subs": ["Seated Calf Raise", "Single-Leg Calf Raise"]},
                    {"exercise": "Bird Dog", "category": "Core", "sets": 3, "reps": 10, "subs": ["Dead Bug", "Pallof Press"]}
                ]
            },
            "Peak": {
                "warmup": [
                    "5 min bike",
                    "Cat-cow x 8",
                    "Quadruped rock-back x 10",
                    "Glute bridge x 12",
                    "Bird dog x 10/side",
                    "Hip flexor mobilization x 10/side",
                    "Ankle rocks x 12/side",
                    "Bodyweight squat x 10",
                    "2-4 ramp-up sets for first lower-body movement"
                ],
                "primary": [
                    {"exercise": "Leg Press", "category": "Quads", "sets": 4, "reps": 6, "subs": ["Hack Squat Machine", "Goblet Squat", "Box Squat"]},
                    {"exercise": "Hamstring Curl", "category": "Hamstrings", "sets": 4, "reps": 8, "subs": ["Stability Ball Curl", "Glute Bridge"]},
                    {"exercise": "Split Squat", "category": "Quads", "sets": 4, "reps": 8, "subs": ["Step-up", "Reverse Lunge"]},
                    {"exercise": "Calf Raise", "category": "Calves", "sets": 4, "reps": 15, "subs": ["Seated Calf Raise", "Single-Leg Calf Raise"]},
                    {"exercise": "Bird Dog", "category": "Core", "sets": 3, "reps": 12, "subs": ["Dead Bug", "Pallof Press"]}
                ]
            }
        },
        "Recovery": {
            "Foundation": {
                "warmup": [
                    "5 min easy walk",
                    "Foam roll T-spine x 45 sec",
                    "Open book x 8/side",
                    "Cat-cow x 8",
                    "Hip flexor stretch x 30 sec/side",
                    "Band pull-aparts x 15",
                    "Dead bug x 8/side"
                ],
                "primary": [
                    {"exercise": "Walk", "category": "Recovery", "sets": 1, "reps": 20, "subs": ["Bike", "Elliptical"]},
                    {"exercise": "Stretch", "category": "Mobility", "sets": 1, "reps": 10, "subs": ["Mobility Flow", "Yoga"]}
                ]
            },
            "Build": {
                "warmup": [
                    "5 min easy walk",
                    "Foam roll T-spine x 45 sec",
                    "Open book x 8/side",
                    "Cat-cow x 8",
                    "Hip flexor stretch x 30 sec/side",
                    "Band pull-aparts x 15",
                    "Dead bug x 8/side"
                ],
                "primary": [
                    {"exercise": "Walk", "category": "Recovery", "sets": 1, "reps": 25, "subs": ["Bike", "Elliptical"]},
                    {"exercise": "Stretch", "category": "Mobility", "sets": 1, "reps": 12, "subs": ["Mobility Flow", "Yoga"]}
                ]
            },
            "Peak": {
                "warmup": [
                    "5 min easy walk",
                    "Foam roll T-spine x 45 sec",
                    "Open book x 8/side",
                    "Cat-cow x 8",
                    "Hip flexor stretch x 30 sec/side",
                    "Band pull-aparts x 15",
                    "Dead bug x 8/side"
                ],
                "primary": [
                    {"exercise": "Walk", "category": "Recovery", "sets": 1, "reps": 30, "subs": ["Bike", "Elliptical"]},
                    {"exercise": "Stretch", "category": "Mobility", "sets": 1, "reps": 15, "subs": ["Mobility Flow", "Yoga"]}
                ]
            }
        },
        "Upper 2": {
            "Foundation": {
                "warmup": [
                    "5 min bike or elliptical",
                    "Foam roll T-spine x 45-60 sec",
                    "Reach-back thoracic rotation x 8/side",
                    "Wall slides x 10",
                    "Band external rotation x 12/side",
                    "Face pull x 12",
                    "Serratus wall slide or scap push-up x 8",
                    "Pallof press x 10/side",
                    "2-3 ramp-up sets for first press and first pull"
                ],
                "primary": [
                    {"exercise": "Incline Machine Press", "category": "Chest", "sets": 3, "reps": 10, "subs": ["Cable Press", "DB Floor Press"]},
                    {"exercise": "Chest-Supported Row", "category": "Back", "sets": 3, "reps": 10, "subs": ["Seated Row", "Cable Row"]},
                    {"exercise": "High Row", "category": "Back", "sets": 3, "reps": 10, "subs": ["Lat Pulldown", "Machine Row"]},
                    {"exercise": "Lateral Raise", "category": "Delts", "sets": 3, "reps": 12, "subs": ["Cable Lateral Raise", "Machine Lateral Raise"]},
                    {"exercise": "Rear Delt Fly", "category": "Rear Delts", "sets": 2, "reps": 15, "subs": ["Face Pull", "Band Pull-Apart"]},
                    {"exercise": "Hammer Curl", "category": "Biceps", "sets": 2, "reps": 12, "subs": ["DB Curl", "Cable Curl"]},
                    {"exercise": "Overhead Rope Extension", "category": "Triceps", "sets": 2, "reps": 12, "subs": ["Cable Pressdown", "Single-Arm Extension"]}
                ]
            },
            "Build": {
                "warmup": [
                    "5 min bike or elliptical",
                    "Foam roll T-spine x 45-60 sec",
                    "Reach-back thoracic rotation x 10/side",
                    "Wall slides x 10",
                    "Band external rotation x 15/side",
                    "Face pull x 15",
                    "Serratus wall slide or scap push-up x 10",
                    "Pallof press x 10/side",
                    "2-3 ramp-up sets for first press and first pull"
                ],
                "primary": [
                    {"exercise": "Incline Machine Press", "category": "Chest", "sets": 4, "reps": 8, "subs": ["Cable Press", "DB Floor Press"]},
                    {"exercise": "Chest-Supported Row", "category": "Back", "sets": 4, "reps": 8, "subs": ["Seated Row", "Cable Row"]},
                    {"exercise": "High Row", "category": "Back", "sets": 4, "reps": 8, "subs": ["Lat Pulldown", "Machine Row"]},
                    {"exercise": "Lateral Raise", "category": "Delts", "sets": 3, "reps": 12, "subs": ["Cable Lateral Raise", "Machine Lateral Raise"]},
                    {"exercise": "Rear Delt Fly", "category": "Rear Delts", "sets": 3, "reps": 12, "subs": ["Face Pull", "Band Pull-Apart"]},
                    {"exercise": "Hammer Curl", "category": "Biceps", "sets": 3, "reps": 10, "subs": ["DB Curl", "Cable Curl"]},
                    {"exercise": "Overhead Rope Extension", "category": "Triceps", "sets": 3, "reps": 10, "subs": ["Cable Pressdown", "Single-Arm Extension"]}
                ]
            },
            "Peak": {
                "warmup": [
                    "5 min bike or elliptical",
                    "Foam roll T-spine x 60 sec",
                    "Reach-back thoracic rotation x 10/side",
                    "Wall slides x 12",
                    "Band external rotation x 15/side",
                    "Face pull x 15",
                    "Serratus wall slide or scap push-up x 10",
                    "Pallof press x 12/side",
                    "2-4 ramp-up sets for first press and first pull"
                ],
                "primary": [
                    {"exercise": "Incline Machine Press", "category": "Chest", "sets": 4, "reps": 6, "subs": ["Cable Press", "DB Floor Press"]},
                    {"exercise": "Chest-Supported Row", "category": "Back", "sets": 4, "reps": 6, "subs": ["Seated Row", "Cable Row"]},
                    {"exercise": "High Row", "category": "Back", "sets": 4, "reps": 8, "subs": ["Lat Pulldown", "Machine Row"]},
                    {"exercise": "Lateral Raise", "category": "Delts", "sets": 4, "reps": 12, "subs": ["Cable Lateral Raise", "Machine Lateral Raise"]},
                    {"exercise": "Rear Delt Fly", "category": "Rear Delts", "sets": 3, "reps": 12, "subs": ["Face Pull", "Band Pull-Apart"]},
                    {"exercise": "Hammer Curl", "category": "Biceps", "sets": 3, "reps": 10, "subs": ["DB Curl", "Cable Curl"]},
                    {"exercise": "Overhead Rope Extension", "category": "Triceps", "sets": 3, "reps": 10, "subs": ["Cable Pressdown", "Single-Arm Extension"]}
                ]
            }
        },
        "Lower 2": {
            "Foundation": {
                "warmup": [
                    "5 min bike",
                    "Cat-cow x 8",
                    "Quadruped rock-back x 10",
                    "Glute bridge x 12",
                    "Bird dog x 8/side",
                    "90/90 hip switches x 8/side",
                    "Ankle rocks x 10/side",
                    "Goblet squat x 8",
                    "2-4 ramp-up sets for first lower-body movement"
                ],
                "primary": [
                    {"exercise": "Hack Squat Machine", "category": "Quads", "sets": 3, "reps": 10, "subs": ["Leg Press", "Goblet Squat"]},
                    {"exercise": "Romanian Deadlift (light)", "category": "Hamstrings", "sets": 3, "reps": 10, "subs": ["Glute Bridge", "Hamstring Curl"]},
                    {"exercise": "Step-up", "category": "Quads", "sets": 3, "reps": 10, "subs": ["Split Squat", "Reverse Lunge"]},
                    {"exercise": "Seated Calf Raise", "category": "Calves", "sets": 3, "reps": 15, "subs": ["Standing Calf Raise", "Single-Leg Calf Raise"]},
                    {"exercise": "Pallof Press", "category": "Core", "sets": 2, "reps": 12, "subs": ["Dead Bug", "Bird Dog"]}
                ]
            },
            "Build": {
                "warmup": [
                    "5 min bike",
                    "Cat-cow x 8",
                    "Quadruped rock-back x 10",
                    "Glute bridge x 12",
                    "Bird dog x 10/side",
                    "90/90 hip switches x 10/side",
                    "Ankle rocks x 10/side",
                    "Goblet squat x 8",
                    "2-4 ramp-up sets for first lower-body movement"
                ],
                "primary": [
                    {"exercise": "Hack Squat Machine", "category": "Quads", "sets": 4, "reps": 8, "subs": ["Leg Press", "Goblet Squat"]},
                    {"exercise": "Romanian Deadlift (light)", "category": "Hamstrings", "sets": 4, "reps": 8, "subs": ["Glute Bridge", "Hamstring Curl"]},
                    {"exercise": "Step-up", "category": "Quads", "sets": 3, "reps": 10, "subs": ["Split Squat", "Reverse Lunge"]},
                    {"exercise": "Seated Calf Raise", "category": "Calves", "sets": 4, "reps": 12, "subs": ["Standing Calf Raise", "Single-Leg Calf Raise"]},
                    {"exercise": "Pallof Press", "category": "Core", "sets": 3, "reps": 12, "subs": ["Dead Bug", "Bird Dog"]}
                ]
            },
            "Peak": {
                "warmup": [
                    "5 min bike",
                    "Cat-cow x 8",
                    "Quadruped rock-back x 10",
                    "Glute bridge x 12",
                    "Bird dog x 10/side",
                    "90/90 hip switches x 10/side",
                    "Ankle rocks x 12/side",
                    "Goblet squat x 8",
                    "2-4 ramp-up sets for first lower-body movement"
                ],
                "primary": [
                    {"exercise": "Hack Squat Machine", "category": "Quads", "sets": 4, "reps": 6, "subs": ["Leg Press", "Goblet Squat"]},
                    {"exercise": "Romanian Deadlift (light)", "category": "Hamstrings", "sets": 4, "reps": 8, "subs": ["Glute Bridge", "Hamstring Curl"]},
                    {"exercise": "Step-up", "category": "Quads", "sets": 4, "reps": 8, "subs": ["Split Squat", "Reverse Lunge"]},
                    {"exercise": "Seated Calf Raise", "category": "Calves", "sets": 4, "reps": 15, "subs": ["Standing Calf Raise", "Single-Leg Calf Raise"]},
                    {"exercise": "Pallof Press", "category": "Core", "sets": 3, "reps": 12, "subs": ["Dead Bug", "Bird Dog"]}
                ]
            }
        },
        "Cardio/Mobility": {
            "Foundation": {
                "warmup": [
                    "5 min brisk walk",
                    "Foam roll T-spine x 45 sec",
                    "Open book x 8/side",
                    "Thread the needle x 8/side",
                    "Shoulder circles x 15 each way",
                    "Hip opener x 8/side",
                    "Dead bug x 8/side"
                ],
                "primary": [
                    {"exercise": "Elliptical", "category": "Conditioning", "sets": 1, "reps": 20, "subs": ["Bike", "Incline Walk"]},
                    {"exercise": "Thoracic Rotation", "category": "Mobility", "sets": 3, "reps": 10, "subs": ["Open Book", "Thread the Needle"]}
                ]
            },
            "Build": {
                "warmup": [
                    "5 min brisk walk",
                    "Foam roll T-spine x 45 sec",
                    "Open book x 8/side",
                    "Thread the needle x 8/side",
                    "Shoulder circles x 15 each way",
                    "Hip opener x 8/side",
                    "Dead bug x 8/side"
                ],
                "primary": [
                    {"exercise": "Elliptical", "category": "Conditioning", "sets": 1, "reps": 25, "subs": ["Bike", "Incline Walk"]},
                    {"exercise": "Thoracic Rotation", "category": "Mobility", "sets": 3, "reps": 12, "subs": ["Open Book", "Thread the Needle"]}
                ]
            },
            "Peak": {
                "warmup": [
                    "5 min brisk walk",
                    "Foam roll T-spine x 45 sec",
                    "Open book x 8/side",
                    "Thread the needle x 8/side",
                    "Shoulder circles x 15 each way",
                    "Hip opener x 8/side",
                    "Dead bug x 8/side"
                ],
                "primary": [
                    {"exercise": "Elliptical", "category": "Conditioning", "sets": 1, "reps": 30, "subs": ["Bike", "Incline Walk"]},
                    {"exercise": "Thoracic Rotation", "category": "Mobility", "sets": 4, "reps": 10, "subs": ["Open Book", "Thread the Needle"]}
                ]
            }
        },
        "Rest": {
            "Foundation": {
                "warmup": [
                    "Optional 10-20 min walk",
                    "Open book x 6/side",
                    "Cat-cow x 6",
                    "Band pull-aparts x 12",
                    "Hip flexor stretch x 20-30 sec/side"
                ],
                "primary": [
                    {"exercise": "Rest", "category": "Recovery", "sets": 1, "reps": 1, "subs": ["Easy Walk", "Stretching"]}
                ]
            },
            "Build": {
                "warmup": [
                    "Optional 10-20 min walk",
                    "Open book x 6/side",
                    "Cat-cow x 6",
                    "Band pull-aparts x 12",
                    "Hip flexor stretch x 20-30 sec/side"
                ],
                "primary": [
                    {"exercise": "Rest", "category": "Recovery", "sets": 1, "reps": 1, "subs": ["Easy Walk", "Stretching"]}
                ]
            },
            "Peak": {
                "warmup": [
                    "Optional 10-20 min walk",
                    "Open book x 6/side",
                    "Cat-cow x 6",
                    "Band pull-aparts x 12",
                    "Hip flexor stretch x 20-30 sec/side"
                ],
                "primary": [
                    {"exercise": "Rest", "category": "Recovery", "sets": 1, "reps": 1, "subs": ["Easy Walk", "Stretching"]}
                ]
            }
        }
    }

# ---------------------------
# Load data
# ---------------------------
workouts_df = load_workouts()
nutrition_df = load_nutrition()

# ---------------------------
# UI
# ---------------------------
st.title("4-Day Upper/Lower Recomp Tracker")

st.header("Program Setup")
c1, c2, c3, c4 = st.columns(4)
with c1:
    start_weight = st.number_input("Starting weight (lbs)", 100.0, 400.0, 168.0, 0.5)
with c2:
    height_inches = st.number_input("Height (inches)", 48.0, 84.0, 70.0, 0.5)
with c3:
    age = st.number_input("Age", 18, 90, 52, 1)
with c4:
    gender = st.selectbox("Gender", ["Male", "Female"])

activity_options = {
    "Sedentary — desk job, little formal exercise, low daily movement": "Sedentary",
    "Lightly Active — 1-3 light workouts/week or modest daily walking": "Lightly Active",
    "Moderately Active — 3-5 training sessions/week with decent daily movement": "Moderately Active",
    "Very Active — hard training most days or physically active job": "Very Active",
    "Extremely Active — very high training volume and/or highly physical lifestyle": "Extremely Active"
}

training_options = {
    "Beginner — less than ~6-12 months of consistent lifting, still learning technique": "Beginner",
    "Intermediate — 1-3+ years of fairly consistent lifting, progressing but no longer rapidly": "Intermediate",
    "Advanced — many years of structured lifting, slower gains, needs more precision": "Advanced"
}

c5, c6, c7, c8 = st.columns(4)
with c5:
    start_date = st.date_input("Program start date", value=date.today())
with c6:
    current_date = st.date_input("Current date in program", value=date.today())
with c7:
    activity_level_label = st.selectbox("Activity level", list(activity_options.keys()))
    activity_level = activity_options[activity_level_label]
with c8:
    training_experience_label = st.selectbox("Training level", list(training_options.keys()))
    training_experience = training_options[training_experience_label]

goal = st.selectbox("Goal", ["Recomp", "Cut", "Bulk"])

days_elapsed = max((current_date - start_date).days, 0)
current_week = min((days_elapsed // 7) + 1, 12)
stage_key, stage_label = get_stage(current_week)
program_end = start_date + timedelta(days=83)

latest_logged_weight = get_latest_logged_weight(start_weight, workouts_df, nutrition_df)
macros = calculate_macros(
    latest_logged_weight, height_inches, age, gender, activity_level, training_experience, goal
)

t1, t2, t3 = st.columns(3)
t1.metric("Current week", current_week)
t2.metric("Current stage", stage_label)
t3.metric("Program end", str(program_end))

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Current bodyweight", f"{latest_logged_weight:.1f} lbs")
m2.metric("Calories", f"{macros['calories']}")
m3.metric("Protein", f"{macros['protein']} g")
m4.metric("Carbs", f"{macros['carbs']} g")
m5.metric("Fat", f"{macros['fat']} g")

program = build_program()
day_options = list(program.keys())
selected_day = st.selectbox("Training day", day_options)
day_plan = program[selected_day][stage_key]

st.header("Daily plan")
left, right = st.columns(2)

with left:
    st.subheader("Warmup")
    st.caption("Warmup order: 1) heat, 2) mobility, 3) activation, 4) ramp-up sets")
    for item in day_plan["warmup"]:
        st.write(f"- {item}")

with right:
    st.subheader("Primary exercises")
    for item in day_plan["primary"]:
        st.write(f"- {item['exercise']} — {item['sets']}x{item['reps']} ({item['category']})")

st.subheader("Possible substitutions")
for item in day_plan["primary"]:
    st.write(f"**{item['exercise']}** → {', '.join(item['subs'])}")

tab1, tab2, tab3, tab4 = st.tabs(["Workout Log", "Nutrition Log", "Dashboard", "Volume Analysis"])

with tab1:
    st.subheader("Log today's exercises")
    workout_date = st.date_input("Workout date", value=current_date, key="workout_date")
    bodyweight_today = st.number_input("Bodyweight today (lbs)", 100.0, 400.0, float(latest_logged_weight), 0.5, key="bw_today")

    for idx, item in enumerate(day_plan["primary"]):
        st.markdown(f"### {item['exercise']}")
        st.caption(f"Suggested substitutions: {', '.join(item['subs'])}")
        options = [item["exercise"]] + item["subs"]
        selected_exercise = st.selectbox(f"Movement choice {idx + 1}", options, key=f"select_{idx}_{selected_day}")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            sets = st.number_input(f"Sets {idx + 1}", 1, 10, item["sets"], key=f"sets_{idx}_{selected_day}")
        with c2:
            reps = st.number_input(f"Reps {idx + 1}", 1, 50, item["reps"], key=f"reps_{idx}_{selected_day}")
        with c3:
            load = st.number_input(f"Load {idx + 1}", 0.0, 1000.0, 0.0, 5.0, key=f"load_{idx}_{selected_day}")
        with c4:
            rpe = st.number_input(f"RPE {idx + 1}", 1.0, 10.0, 7.0, 0.5, key=f"rpe_{idx}_{selected_day}")
        notes = st.text_input(f"Notes {idx + 1}", key=f"notes_{idx}_{selected_day}")

        if st.button(f"Save {selected_exercise}", key=f"save_{idx}_{selected_day}"):
            row = {
                "Date": workout_date,
                "Week": current_week,
                "Stage": stage_key,
                "Day": selected_day,
                "Bodyweight": bodyweight_today,
                "Primary Exercise": item["exercise"],
                "Selected Exercise": selected_exercise,
                "Category": item["category"],
                "Sets": sets,
                "Reps": reps,
                "Load": load,
                "RPE": rpe,
                "Notes": notes
            }
            insert_workout(row)
            st.success(f"Saved {selected_exercise}")
            st.rerun()

    with st.form("custom_exercise_form"):
        st.markdown("### Add custom exercise")
        extra_name = st.text_input("Custom exercise name")
        category = st.selectbox("Body-part category", ["Chest", "Back", "Delts", "Rear Delts", "Biceps", "Triceps", "Quads", "Hamstrings", "Calves", "Core", "Mobility", "Conditioning", "Recovery", "Custom"])
        e1, e2, e3, e4 = st.columns(4)
        with e1:
            extra_sets = st.number_input("Custom sets", 1, 10, 3)
        with e2:
            extra_reps = st.number_input("Custom reps", 1, 50, 10)
        with e3:
            extra_load = st.number_input("Custom load", 0.0, 1000.0, 0.0, 5.0)
        with e4:
            extra_rpe = st.number_input("Custom RPE", 1.0, 10.0, 7.0, 0.5)
        extra_notes = st.text_input("Custom notes")
        submit_extra = st.form_submit_button("Save custom exercise")

        if submit_extra and extra_name:
            row = {
                "Date": workout_date,
                "Week": current_week,
                "Stage": stage_key,
                "Day": selected_day,
                "Bodyweight": bodyweight_today,
                "Primary Exercise": "Custom",
                "Selected Exercise": extra_name,
                "Category": category,
                "Sets": extra_sets,
                "Reps": extra_reps,
                "Load": extra_load,
                "RPE": extra_rpe,
                "Notes": extra_notes
            }
            insert_workout(row)
            st.success(f"Saved custom exercise: {extra_name}")
            st.rerun()

    workouts_df = load_workouts()
    st.dataframe(workouts_df, use_container_width=True)

with tab2:
    st.subheader("Log nutrition")
    with st.form("nutrition_form"):
        n1, n2, n3, n4, n5, n6 = st.columns(6)
        with n1:
            nutrition_date = st.date_input("Nutrition date", value=current_date, key="nutrition_date")
        with n2:
            nutrition_bw = st.number_input("Bodyweight", 100.0, 400.0, float(latest_logged_weight), 0.5)
        with n3:
            calories_in = st.number_input("Calories eaten", 0, 10000, macros["calories"])
        with n4:
            protein_in = st.number_input("Protein eaten", 0, 500, macros["protein"])
        with n5:
            carbs_in = st.number_input("Carbs eaten", 0, 1000, macros["carbs"])
        with n6:
            fat_in = st.number_input("Fat eaten", 0, 300, macros["fat"])
        submitted_nutrition = st.form_submit_button("Save nutrition")

        if submitted_nutrition:
            row = {
                "Date": nutrition_date,
                "Week": current_week,
                "Bodyweight": nutrition_bw,
                "Calories": calories_in,
                "Protein": protein_in,
                "Carbs": carbs_in,
                "Fat": fat_in,
                "Target Calories": macros["calories"],
                "Target Protein": macros["protein"],
                "Target Carbs": macros["carbs"],
                "Target Fat": macros["fat"]
            }
            insert_nutrition(row)
            st.success("Nutrition saved")
            st.rerun()

    nutrition_df = load_nutrition()
    st.dataframe(nutrition_df, use_container_width=True)

with tab3:
    st.subheader("Progress dashboard")

    if not workouts_df.empty:
        chart_df = workouts_df.copy()
        if "Date" in chart_df.columns:
            chart_df["Date"] = pd.to_datetime(chart_df["Date"], errors="coerce")
        if "Sets" in chart_df.columns:
            chart_df["Sets"] = pd.to_numeric(chart_df["Sets"], errors="coerce")
        if "Reps" in chart_df.columns:
            chart_df["Reps"] = pd.to_numeric(chart_df["Reps"], errors="coerce")
        if "Load" in chart_df.columns:
            chart_df["Load"] = pd.to_numeric(chart_df["Load"], errors="coerce")
        if "RPE" in chart_df.columns:
            chart_df["RPE"] = pd.to_numeric(chart_df["RPE"], errors="coerce")
        chart_df = chart_df.dropna(subset=["Date", "Reps", "Load", "RPE"])

        if not chart_df.empty:
            fig_workouts = px.scatter(
                chart_df,
                x="Reps",
                y="Load",
                color="Selected_Exercise",
                size="RPE",
                hover_data=["Date", "Sets", "Day", "Category"],
                title="Workout progression"
            )
            st.plotly_chart(fig_workouts, use_container_width=True)

            vol_df = chart_df.copy()
            vol_df["Volume"] = vol_df["Sets"] * vol_df["Reps"] * vol_df["Load"]
            fig_volume = px.bar(
                vol_df.groupby("Selected_Exercise", as_index=False)["Volume"].sum(),
                x="Selected_Exercise",
                y="Volume",
                title="Total training volume by exercise"
            )
            st.plotly_chart(fig_volume, use_container_width=True)

    if not nutrition_df.empty:
        nut_df = nutrition_df.copy()
        if "Date" in nut_df.columns:
            nut_df["Date"] = pd.to_datetime(nut_df["Date"], errors="coerce")
        if "Calories" in nut_df.columns:
            nut_df["Calories"] = pd.to_numeric(nut_df["Calories"], errors="coerce")
        if "Protein" in nut_df.columns:
            nut_df["Protein"] = pd.to_numeric(nut_df["Protein"], errors="coerce")
        if "Bodyweight" in nut_df.columns:
            nut_df["Bodyweight"] = pd.to_numeric(nut_df["Bodyweight"], errors="coerce")
        nut_df = nut_df.dropna(subset=["Date"])

        d1, d2 = st.columns(2)
        d1.metric("Average calories logged", f"{nut_df['Calories'].mean():.0f}")
        d2.metric("Average protein logged", f"{nut_df['Protein'].mean():.0f} g")

        fig_nutrition = px.line(
            nut_df,
            x="Date",
            y=["Calories", "Protein", "Bodyweight"],
            title="Nutrition and bodyweight trend"
        )
        st.plotly_chart(fig_nutrition, use_container_width=True)

with tab4:
    st.subheader("Weekly set volume analysis")
    targets = calculate_weekly_set_targets(goal, training_experience)

    if workouts_df.empty:
        st.info("Log workouts to see weekly set analysis.")
    else:
        analysis_df = workouts_df.copy()
        if "Week" in analysis_df.columns:
            analysis_df["Week"] = pd.to_numeric(analysis_df["Week"], errors="coerce")
        if "Sets" in analysis_df.columns:
            analysis_df["Sets"] = pd.to_numeric(analysis_df["Sets"], errors="coerce")
        analysis_df = analysis_df.dropna(subset=["Week", "Sets", "Category"])

        week_values = sorted(analysis_df["Week"].dropna().astype(int).unique().tolist())
        if week_values:
            week_filter = st.selectbox("Analyze week", week_values, index=0)
            week_df = analysis_df[analysis_df["Week"] == week_filter]
            by_category = week_df.groupby("Category", as_index=False)["Sets"].sum()

            rows = []
            for category, target_range in targets.items():
                actual_sets = 0
                match = by_category[by_category["Category"] == category]
                if not match.empty:
                    actual_sets = float(match.iloc[0]["Sets"])

                low_target, high_target = target_range
                if actual_sets < low_target:
                    status = "Under target"
                elif actual_sets > high_target:
                    status = "Above target"
                else:
                    status = "On target"

                rows.append({
                    "Category": category,
                    "Actual Sets": actual_sets,
                    "Target Range": f"{low_target}-{high_target}",
                    "Status": status
                })

            result_df = pd.DataFrame(rows)
            st.dataframe(result_df, use_container_width=True)

            fig_sets = px.bar(
                result_df,
                x="Category",
                y="Actual Sets",
                color="Status",
                title=f"Weekly set totals - Week {week_filter}"
            )
            st.plotly_chart(fig_sets, use_container_width=True)

st.markdown("---")
st.write(
    f"Current plan: {goal} | {stage_label} | bodyweight driving macros: {latest_logged_weight:.1f} lbs | "
    f"targets: {macros['calories']} cal, {macros['protein']} g protein, {macros['carbs']} g carbs, {macros['fat']} g fat."
)
