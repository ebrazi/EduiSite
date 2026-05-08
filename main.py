import os
import sys
import random
import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import threading
import time

# ==========================================
# --- SUMO Environment Setup ---
# ==========================================
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")
import traci

# ==========================================
# --- Simulation Parameters ---
# ==========================================
SUMO_BINARY = "sumo"
# مسیر فایل کانفیگ خود را در خط زیر آپدیت کنید
SUMO_CMD =[SUMO_BINARY, "-c", r"C:\Users\Roozbeh\pythonTest\SUMO_Simulation_2\sim.sumocfg", "--step-length", "0.5", "--start"]
ROAD_ID = "highway"
ROAD_LENGTH = 5000.0
DT = 0.5  
SIMULATION_DURATION_PER_DAY = 3600 
NUM_SEGMENTS = 10
SEGMENT_LENGTH = ROAD_LENGTH / NUM_SEGMENTS

# ==========================================
# --- Global Memory for Commuters ---
# ==========================================
GLOBAL_COMMUTER_MEMORY = {}
TOTAL_COMMUTERS = 1000  
COMMUTER_RATIO = 0.8    

# ==========================================
# --- Behavioral Parameters (4-Layer Model) ---
# ==========================================
V_FREE_RANGE = (30.0, 38.0)      # m/s (~108 to 137 km/h)
LAMBDA_S = 0.05                  # نرخ فراموشی حافظه کوتاه مدت (سریع)
LAMBDA_L = 0.001                 # نرخ فراموشی حافظه بلند مدت (کند)
W_S, W_L = 0.7, 0.3              # وزن‌های حافظه کوتاه و بلند در ادراک ریسک
BETA_RANGE = (0.2, 0.4)          # حداکثر ضریب کاهش سرعت (مثلا تا ۴۰٪ سرعت کم کند)
THETA_RANGE = (0.3, 0.6)         # آستانه تحمل ریسک راننده
K_SENSITIVITY = 10.0             # شیب تابع سیگموئید
ETA_RANGE = (0.1, 0.4)           # ضریب تاثیرپذیری اجتماعی
POLICE_PERCEPTION_RADIUS = 150.0 
SOCIAL_INFLUENCE_RADIUS = 100.0  

def sigmoid(x):
    """تابع سیگموئید برای مدل‌سازی آستانه واکنش"""
    if x > 10: return 1.0
    if x < -10: return 0.0
    return 1 / (1 + math.exp(-x))

# ==========================================
# --- Cognitive Driver Agent ---
# ==========================================
class DriverAgent:
    def __init__(self, veh_id):
        self.id = veh_id
        
        # تعیین هویت راننده (بومی یا عبوری)
        self.is_commuter = random.random() < COMMUTER_RATIO
        if self.is_commuter:
            self.commuter_id = random.randint(1, TOTAL_COMMUTERS)
            # خواندن حافظه بلندمدت از روزهای قبل
            self.Ml = GLOBAL_COMMUTER_MEMORY.get(self.commuter_id, {}).copy()
        else:
            self.commuter_id = None
            self.Ml = {} 
            
        # پارامترهای ذاتی راننده
        self.v_free = random.uniform(*V_FREE_RANGE)
        self.beta = random.uniform(*BETA_RANGE)
        self.theta = random.uniform(*THETA_RANGE)
        self.eta = random.uniform(*ETA_RANGE)
        
        self.Ms = 0.0 # حافظه کوتاه مدت همیشه صفر شروع می‌شود
        
    def step(self, police_positions_1d):
        try:
            # پیدا کردن مختصات X مطلق ماشین در کل جاده
            pos_x = traci.vehicle.getPosition(self.id)[0] 
            segment_id = int(pos_x / SEGMENT_LENGTH)

            # آیا پلیس در دیدرس است؟
            I_seen = 0.0
            for pol_pos in police_positions_1d:
                if abs(pos_x - pol_pos) < POLICE_PERCEPTION_RADIUS:
                    I_seen = 1.0
                    break

            # ----------------------------------------------------
            # LAYER 1: Dual-Memory Dynamics
            # ----------------------------------------------------
            # الف) حافظه کوتاه مدت (ترس لحظه ای)
            self.Ms = (self.Ms * math.exp(-LAMBDA_S * DT)) + I_seen
            self.Ms = min(1.0, self.Ms) 
            
            # ب) حافظه بلند مدت (فقط برای قطعه فعلی آپدیت می‌شود)
            current_Ml = self.Ml.get(segment_id, 0.0)
            self.Ml[segment_id] = (current_Ml * math.exp(-LAMBDA_L * DT)) + I_seen
            self.Ml[segment_id] = min(1.0, self.Ml[segment_id])

            # ----------------------------------------------------
            # LAYER 2: Risk Perception
            # ----------------------------------------------------
            Omega = (W_S * self.Ms) + (W_L * self.Ml.get(segment_id, 0.0))
            Omega = min(1.0, Omega)

            # ----------------------------------------------------
            # LAYER 3: Speed Choice (Bounded Rationality)
            # ----------------------------------------------------
            compliance = sigmoid(K_SENSITIVITY * (Omega - self.theta))
            v_target = self.v_free * (1 - (self.beta * compliance))

            # ----------------------------------------------------
            # LAYER 4: Peer Effect (Social Adaptation)
            # ----------------------------------------------------
            neighbors_data = traci.vehicle.getNeighbors(self.id, 1) # ماشین‌های جلویی
            v_neighbors =[]
            
            for neighbor_id, dist in neighbors_data:
                if dist <= SOCIAL_INFLUENCE_RADIUS:
                    try:
                        v_neighbors.append(traci.vehicle.getSpeed(neighbor_id))
                    except traci.TraCIException:
                        pass
            
            if v_neighbors:
                v_avg_neighbors = np.mean(v_neighbors)
                v_final = ((1 - self.eta) * v_target) + (self.eta * v_avg_neighbors)
            else:
                v_final = v_target
                
            # اعمال سرعت مطلوب به SUMO (برای رعایت فیزیک تصادفات از setMaxSpeed استفاده می کنیم)
            traci.vehicle.setMaxSpeed(self.id, max(5.0, v_final))
            
            # ذخیره در حافظه جهانی برای روزهای بعد
            if self.is_commuter:
                GLOBAL_COMMUTER_MEMORY[self.commuter_id] = self.Ml.copy()

        except traci.TraCIException:
            pass

# ==========================================
# --- Police Deployment Manager ---
# ==========================================
class PoliceDeployment:
    def __init__(self, road_id, road_len):
        self.road_id = road_id
        self.road_len = road_len
        self.poi_ids =[]

    def clear_police(self):
        for poi_id in self.poi_ids:
            try:
                if poi_id in traci.poi.getIDList():
                    traci.poi.remove(poi_id)
            except traci.TraCIException:
                continue
        self.poi_ids =[]

    def place_police_at(self, positions):
        self.clear_police()
        police_locations_2d, police_locations_1d = [],[]
        for i, pos in enumerate(positions):
            poi_id = f"police_{i}"
            try:
                x, y = traci.simulation.convert2D(self.road_id, pos)
                traci.poi.add(poi_id, x, y, color=(255, 0, 0, 255)) 
                self.poi_ids.append(poi_id)
                police_locations_2d.append((x,y))
                police_locations_1d.append(pos) 
            except traci.TraCIException:
                continue
        return police_locations_2d, police_locations_1d

    def apply_policy(self, policy_name, t, params=None):
        params = params or {}
        n_police = params.get("n_police", 2)
        
        positions =[]
        if policy_name == "block":
            if n_police > 0:
                positions =[i * (self.road_len / n_police) + (self.road_len / n_police) / 2 for i in range(n_police)]
        elif policy_name == "sinusoidal":
            amp = params.get("amplitude", 1000)
            freq = params.get("frequency", 0.005)
            if n_police > 0:
                positions =[(i * (self.road_len/n_police) + amp * math.sin(freq * t + i * math.pi/2)) % self.road_len for i in range(n_police)]
        elif policy_name == "patrolling":
            wp = params.get("waypoints", [500, 2500, 4500])
            dt_dwell = params.get("dwell_time", 180) 
            if n_police >= 1 and wp:
                idx = int((t // dt_dwell) % len(wp))
                positions = [wp[idx]]
        elif policy_name == "single_point":
            positions =[self.road_len / 2.0] if n_police >= 1 else[]
        
        return self.place_police_at(positions) if positions else ([],[])

# ==========================================
# --- Simulation Loop ---
# ==========================================
def run_single_day_simulation(day_number, policy_name, policy_params):
    traci.start(SUMO_CMD)
    drivers = {} 
    police_deployer = PoliceDeployment(ROAD_ID, ROAD_LENGTH)
    speed_data_history, police_pos_history = [],[]
    
    t_now = 0.0
    while t_now < SIMULATION_DURATION_PER_DAY:
        traci.simulationStep()
        t_now = traci.simulation.getTime()
        
        # Absolute time isn't strictly needed for exponential decay in this step-by-step logic, 
        # but kept for reference if needed for logging
        absolute_t = t_now + (day_number * SIMULATION_DURATION_PER_DAY)
        
        pos_2d, pos_1d = police_deployer.apply_policy(policy_name, absolute_t, policy_params)
        if pos_1d: 
            police_pos_history.append({'time': t_now, 'positions': pos_1d})
        
        for veh_id in traci.simulation.getDepartedIDList():
            drivers[veh_id] = DriverAgent(veh_id)
                
        for veh_id in traci.simulation.getArrivedIDList():
            if veh_id in drivers:
                del drivers[veh_id]
            
        for veh_id, driver in list(drivers.items()): 
            driver.step(pos_1d) # فراخوانی تابع ۴ لایه‌ای در هر استپ
            
            try:
                speed = traci.vehicle.getSpeed(veh_id)
                pos_x = traci.vehicle.getPosition(veh_id)[0]
                segment = int(pos_x / SEGMENT_LENGTH)
                speed_data_history.append({'time': t_now, 'segment': segment, 'speed': speed})
            except traci.TraCIException: 
                if veh_id in drivers:
                    del drivers[veh_id]
                continue
                
    traci.close()
    return speed_data_history, police_pos_history

# ==========================================
# --- Plotting and Visualization ---
# ==========================================
def generate_visualizations(results, num_segments=10):
    all_segment_speeds_df = pd.DataFrame()
    for policy_name, result in results.items():
        print(f"\n--- Generating Heatmap for Policy: {policy_name} ---")
        heatmap_df = result['heatmap_data']
        police_df = pd.DataFrame(result['police_data'])
        plt.figure(figsize=(12, 8))
        ax = sns.heatmap(heatmap_df, cmap="viridis_r", cbar_kws={'label': 'Average Speed (km/h)'})
        
        if not police_df.empty:
            time_bin_size = result['time_bin_size']
            for _, row in police_df.iterrows():
                time_bin = int(row['time'] / time_bin_size)
                if 0 <= time_bin < heatmap_df.shape[0]:
                    for pos in row['positions']:
                        segment_idx = int(pos / SEGMENT_LENGTH)
                        if 0 <= segment_idx < num_segments:
                            ax.scatter(segment_idx + 0.5, time_bin + 0.5, marker='X', color='red', s=100, ec='white', lw=1.5, label='Police')
        
        handles, labels = ax.get_legend_handles_labels()
        if labels:
            by_label = dict(zip(labels, handles))
            ax.legend(by_label.values(), by_label.keys(), loc='upper right')
        
        ax.set_title(f'Speed Heatmap\nPolicy: {policy_name} (Based on {result["days_completed"]} days)', fontsize=16)
        ax.set_xlabel('Road Segment', fontsize=12)
        ax.set_ylabel(f'Time Bins ({result["time_bin_size"]}s)', fontsize=12)
        plt.tight_layout()
        plt.savefig(f"heatmap_{policy_name.replace(' ', '_')}.png")
        plt.show()
        
        policy_avg_speeds = heatmap_df.mean(axis=0)
        policy_avg_speeds.name = policy_name
        all_segment_speeds_df = pd.concat([all_segment_speeds_df, policy_avg_speeds], axis=1)

    print("\n--- Generating Comparison Plot ---")
    plt.figure(figsize=(14, 7))
    all_segment_speeds_df.plot(kind='line', marker='o', ax=plt.gca())
    plt.title('Comparison of Average Speed per Segment Across Policies', fontsize=16)
    plt.xlabel('Road Segment', fontsize=12)
    plt.ylabel('Overall Average Speed (km/h)', fontsize=12)
    plt.xticks(range(num_segments))
    plt.grid(True, which='both', linestyle='--', linewidth=0.5)
    plt.legend(title='Policy')
    plt.tight_layout()
    plt.savefig("comparison_plot.png")
    plt.show()

class InputThread(threading.Thread):
    def run(self):
        try: input()
        except EOFError: pass

# ==========================================
# --- Main Execution ---
# ==========================================
def main():
    NUM_SIMULATION_DAYS = 2 
    INTERACTIVE_TIMEOUT = 4 
    TIME_BIN_SIZE = 60 
    
    policies_to_run = {
        "Single Point Police":  {"name": "single_point", "params": {"n_police": 1}}, 
        "No Police (Baseline)": {"name": "none", "params": {}},
        "Static (Block)":       {"name": "block", "params": {"n_police": 2}},
        "Dynamic (Sinusoidal)": {"name": "sinusoidal", "params": {"n_police": 2, "amplitude": 1200}},
    }
    
    all_policy_results = {} 

    for policy_title, config in policies_to_run.items():
        print(f"\n=================================================")
        print(f"Running Simulation for Policy: {policy_title}")
        print(f"=================================================")
        
        # Reset Global Memory for each new policy test to ensure fair comparison
        global GLOBAL_COMMUTER_MEMORY
        GLOBAL_COMMUTER_MEMORY = {}

        full_police_data =[] 
        num_time_bins = int(SIMULATION_DURATION_PER_DAY / TIME_BIN_SIZE)
        heatmap_sum = np.zeros((num_time_bins, NUM_SEGMENTS)) 
        heatmap_count = np.zeros((num_time_bins, NUM_SEGMENTS), dtype=int) 
        
        days_completed = 0
        for day in range(NUM_SIMULATION_DAYS):
            days_completed += 1
            print(f"--- Day {day + 1}/{NUM_SIMULATION_DAYS} ---")
            
            daily_speed_data, daily_police_data = run_single_day_simulation(
                day_number=day,
                policy_name=config['name'], 
                policy_params=config['params']
            )
            
            for record in daily_speed_data:
                time_bin = int(record['time'] // TIME_BIN_SIZE)
                if 0 <= time_bin < num_time_bins:
                    segment = record['segment']
                    if 0 <= segment < NUM_SEGMENTS:
                        heatmap_sum[time_bin, segment] += record['speed']
                        heatmap_count[time_bin, segment] += 1
            del daily_speed_data 
            
            full_police_data.extend(daily_police_data) 
            
            if day < NUM_SIMULATION_DAYS - 1:
                print(f"\nDay {day + 1} finished. Pausing for {INTERACTIVE_TIMEOUT} seconds...")
                it = InputThread()
                it.start()
                it.join(timeout=INTERACTIVE_TIMEOUT)
                if not it.is_alive():
                    print("User interrupted. Generating report with data collected so far...\n")
                    break 
        
        with np.errstate(divide='ignore', invalid='ignore'): 
            heatmap_avg_speed = np.divide(heatmap_sum, heatmap_count)
        heatmap_avg_speed[np.isnan(heatmap_avg_speed)] = 0 
        heatmap_avg_speed *= 3.6 # Convert to km/h
        
        heatmap_df = pd.DataFrame(heatmap_avg_speed, columns=[f'{i}' for i in range(NUM_SEGMENTS)])

        all_policy_results[policy_title] = {
            "heatmap_data": heatmap_df,
            "police_data": full_police_data,
            "days_completed": days_completed,
            "time_bin_size": TIME_BIN_SIZE
        }

    generate_visualizations(all_policy_results)
    print("\nAnalysis Finished. Check the generated PNG files.")

if __name__ == "__main__":
    main()