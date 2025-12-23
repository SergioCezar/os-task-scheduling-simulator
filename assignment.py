import argparse
import multiprocessing
import socket
import time
import math
import select
from collections import deque
from dataclasses import dataclass, field
import matplotlib.pyplot as plt
import heapq

# --- CONSTANTES DE CONFIGURAÇÃO ---
CLOCK_PORT = 4000
EMITTER_PORT = 4001
SCHEDULER_PORT = 4002
HOST = 'localhost'
MESSAGE_DELIMITER = "||"

# --- DEFINIÇÃO DA ESTRUTURA DE TAREFA ---
@dataclass
class Task:
    id: str
    arrival_time: int
    duration: int
    priority: int
    remaining_time: int = field(init=False)
    initial_priority: int = field(init=False)
    start_time: int = -1
    finish_time: int = -1
    turnaround_time: int = 0
    waiting_time: int = 0

    def __post_init__(self):
        self.remaining_time = self.duration
        self.initial_priority = self.priority

# --- LÓGICA DOS PROCESSOS (Clock e Emissor) ---
def clock_process(scheduler_ready_event, emitter_ready_event):
    scheduler_ready_event.wait()
    emitter_ready_event.wait()

    current_time = 0
    running = True
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, CLOCK_PORT))
    server_socket.listen(1)
    server_socket.setblocking(False)

    try:
        emitter_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        scheduler_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        emitter_client.connect((HOST, EMITTER_PORT))
        scheduler_client.connect((HOST, SCHEDULER_PORT))
    except ConnectionRefusedError:
        print("Clock: Falha fatal ao conectar. Verifique se os outros processos iniciaram. Encerrando.")
        server_socket.close()
        return

    while running:
        ready_to_read, _, _ = select.select([server_socket], [], [], 0)
        if ready_to_read:
            conn, _ = server_socket.accept()
            msg = conn.recv(1024).decode()
            if "END_SIMULATION" in msg:
                running = False
            conn.close()
        
        if not running:
            break

        time.sleep(0.1) # Simula o tick de 100ms
        
        try:
            message_to_send = f"CLOCK|{current_time}{MESSAGE_DELIMITER}".encode()
            emitter_client.sendall(message_to_send)
            time.sleep(0.005) # Atraso de 5ms conforme especificação
            scheduler_client.sendall(message_to_send)
        except (BrokenPipeError, ConnectionResetError):
            print("Clock: Conexão perdida com o escalonador/emissor. Encerrando.")
            running = False
            
        current_time += 1
            
    print("Clock: Processo encerrado.")
    emitter_client.close()
    scheduler_client.close()
    server_socket.close()

def emitter_process(input_file, emitter_ready_event):
    tasks_to_emit = []
    try:
        with open(input_file, 'r') as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    parts = line.strip().split(';')
                    tasks_to_emit.append(Task(id=parts[0], arrival_time=int(parts[1]), duration=int(parts[2]), priority=int(parts[3])))
    except FileNotFoundError:
        print(f"Emissor: Arquivo de entrada '{input_file}' não encontrado.")
        return
    
    tasks_to_emit.sort(key=lambda t: t.arrival_time)
    all_tasks_sent = False
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, EMITTER_PORT))
    server_socket.listen(2)
    
    emitter_ready_event.set()
    
    try:
        scheduler_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        scheduler_client.connect((HOST, SCHEDULER_PORT))
    except ConnectionRefusedError:
        print("Emissor: Não foi possível conectar ao escalonador. Encerrando.")
        server_socket.close()
        return

    inputs = {server_socket}
    running = True
    buffer_data = ""

    while running:
        readable, _, _ = select.select(list(inputs), [], [], 0.1)
        for s in readable:
            if s is server_socket:
                conn, _ = s.accept()
                inputs.add(conn)
            else:
                try:
                    data = s.recv(1024).decode()
                    if not data:
                        inputs.remove(s)
                        s.close()
                        continue
                    
                    buffer_data += data
                    while MESSAGE_DELIMITER in buffer_data:
                        message, buffer_data = buffer_data.split(MESSAGE_DELIMITER, 1)
                        if not message: continue

                        if "END_SIMULATION" in message:
                            running = False
                            break
                        
                        msg_type, msg_payload = message.split('|')
                        if msg_type == "CLOCK":
                            current_time = int(msg_payload)
                            tasks_ready_now = [t for t in tasks_to_emit if t.arrival_time == current_time]
                            for task in tasks_ready_now:
                                task_str = f"NEW_TASK|{task.id};{task.arrival_time};{task.duration};{task.priority}{MESSAGE_DELIMITER}"
                                scheduler_client.sendall(task_str.encode())
                                tasks_to_emit.remove(task)
                            
                            if not tasks_to_emit and not all_tasks_sent:
                                scheduler_client.sendall(f"ALL_TASKS_SENT|{MESSAGE_DELIMITER}".encode())
                                all_tasks_sent = True
                except (socket.error, ValueError, ConnectionResetError):
                    inputs.remove(s)
                    s.close()
    
    print("Emissor: Processo encerrado.")
    scheduler_client.close()
    for s in inputs:
        s.close()

# --- FUNÇÕES AUXILIARES DE SAÍDA ---
def write_output_file(output_filename, timeline, finished_tasks, algorithm):
    with open(output_filename, "w") as f:
        f.write(";".join(timeline) + "\n")
        total_turnaround, total_waiting_time = 0, 0
        
        finished_tasks.sort(key=lambda t: (t.arrival_time, t.id))
            
        for task in finished_tasks:
            f.write(f"{task.id};{task.arrival_time};{task.finish_time};{task.turnaround_time};{task.waiting_time}\n")
            total_turnaround += task.turnaround_time
            total_waiting_time += task.waiting_time
        
        num_tasks = len(finished_tasks)
        if num_tasks > 0:
            avg_turnaround = math.ceil((total_turnaround / num_tasks) * 10) / 10
            avg_waiting_time = math.ceil((total_waiting_time / num_tasks) * 10) / 10
            f.write(f"{avg_turnaround:.1f};{avg_waiting_time:.1f}\n")
        else:
            f.write("0.0;0.0\n")
    print(f"Arquivo de saída salvo como: {output_filename}")

def generate_gantt_chart(timeline, algorithm_name):
    try:
        tasks = sorted(list(set(task for task in timeline if task != '-')), key=lambda x: int(''.join(filter(str.isdigit, x))) if any(char.isdigit() for char in x) else 999)
    except (ValueError, TypeError):
        return

    if not tasks:
        return

    colors = plt.cm.get_cmap('viridis', len(tasks))
    color_map = {task: colors(i) for i, task in enumerate(tasks)}
    color_map['-'] = 'white'

    fig, ax = plt.subplots(figsize=(15, 5))
    
    if not timeline: return
    
    start_time = 0
    current_task_id = timeline[0]
    for i in range(1, len(timeline)):
        if timeline[i] != current_task_id:
            if current_task_id != '-':
                try:
                    y_pos = tasks.index(current_task_id)
                    ax.barh(y_pos, i - start_time, left=start_time, height=0.6, align='center', color=color_map.get(current_task_id, 'gray'), edgecolor='black')
                except ValueError: pass
            start_time = i
            current_task_id = timeline[i]
    
    if current_task_id != '-':
        try:
            y_pos = tasks.index(current_task_id)
            ax.barh(y_pos, len(timeline) - start_time, left=start_time, height=0.6, align='center', color=color_map.get(current_task_id, 'gray'), edgecolor='black')
        except ValueError: pass

    ax.set_yticks(range(len(tasks)))
    ax.set_yticklabels(tasks)
    ax.invert_yaxis()
    ax.set_xlabel("Ciclos de Clock (Tempo)")
    ax.set_title(f"Diagrama de Gantt - Algoritmo {algorithm_name.upper()}")
    ax.set_xticks(range(0, len(timeline) + 1, max(1, len(timeline) // 20)))
    ax.grid(True, which='both', linestyle='--', linewidth=0.5, axis='x')
    
    plt.tight_layout()
    output_filename = f"gantt_{algorithm_name}.png"
    plt.savefig(output_filename)
    plt.close()
    print(f"Diagrama de Gantt salvo como: {output_filename}")

# --- LÓGICA DO PROCESSO ESCALONADOR  ---
def scheduler_process(algorithm, scheduler_ready_event):
    is_priority_based = algorithm in ['sjf', 'srtf', 'prioc', 'priop', 'priod']
    is_preemptive = algorithm in ['srtf', 'priop', 'priod', 'rr']
    
    # Usa heapq (implementado como uma lista) para algoritmos de prioridade e deque para FCFS/RR
    ready_queue = [] if is_priority_based else deque()
    
    finished_tasks = []
    current_task = None
    timeline = []
    all_tasks_emitted = False
    quantum = 3
    quantum_slice = 0
    last_clock_time = -1

    # Configuração do socket do servidor
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setblocking(False)
    server_socket.bind((HOST, SCHEDULER_PORT))
    server_socket.listen(5)
    scheduler_ready_event.set()

    inputs = [server_socket]
    socket_buffers = {}
    running = True

    # Função auxiliar para criar itens para o heap
    def make_heap_item(task):
        if algorithm == 'sjf':
            return [task.duration, task.arrival_time, task.id, task]
        if algorithm == 'srtf':
            return [task.remaining_time, task.arrival_time, task.id, task]
        if algorithm in ['prioc', 'priop', 'priod']:
            return [task.priority, task.arrival_time, task.id, task]
        return None

    while running:
        if all_tasks_emitted and not ready_queue and not current_task:
            running = False
            continue

        readable, _, _ = select.select(inputs, [], [], 0.05)

        for s in readable:
            if s is server_socket:
                conn, addr = s.accept()
                conn.setblocking(False)
                inputs.append(conn)
                socket_buffers[conn] = b""
            else:
                try:
                    data = s.recv(1024)
                    if not data:
                        if s in inputs: inputs.remove(s)
                        s.close()
                        continue

                    socket_buffers[s] += data
                    while MESSAGE_DELIMITER.encode() in socket_buffers[s]:
                        message_bytes, socket_buffers[s] = socket_buffers[s].split(MESSAGE_DELIMITER.encode(), 1)
                        message = message_bytes.decode()
                        if not message: continue
                        
                        parts = message.split('|', 1)
                        msg_type, msg_payload = parts[0], parts[1] if len(parts) > 1 else ""

                        if msg_type == "NEW_TASK":
                            t_id, t_arrival, t_duration, t_priority = msg_payload.split(';')
                            new_task = Task(id=t_id, arrival_time=int(t_arrival), duration=int(t_duration), priority=int(t_priority))
                            if is_priority_based:
                                heapq.heappush(ready_queue, make_heap_item(new_task))
                            else:
                                ready_queue.append(new_task)

                        elif msg_type == "ALL_TASKS_SENT":
                            all_tasks_emitted = True

                        elif msg_type == "CLOCK":
                            current_time = int(msg_payload)
                            if current_time <= last_clock_time: continue
                            last_clock_time = current_time

                            # --- LÓGICA DE ESCALONAMENTO POR CLOCK ---

                            # 1. ATUALIZAÇÃO DE ESTADO (PRIOD)
                            if algorithm == 'priod' and ready_queue:
                                for item in ready_queue:
                                    if item[0] > 0:  # item[0] é a prioridade
                                        item[0] -= 1
                                heapq.heapify(ready_queue)

                            # 2. VERIFICA TAREFA CONCLUÍDA
                            if current_task and current_task.remaining_time <= 0:
                                current_task.finish_time = current_time
                                current_task.turnaround_time = current_task.finish_time - current_task.arrival_time
                                current_task.waiting_time = current_task.turnaround_time - current_task.duration
                                finished_tasks.append(current_task)
                                current_task = None
                                quantum_slice = 0
                            
                            # 3. VERIFICA PREEMPÇÃO (RR ou PREEMPTIVOS DE PRIORIDADE)
                            # Preempção do Round-Robin
                            if algorithm == 'rr' and current_task and quantum_slice >= quantum:
                                ready_queue.append(current_task)
                                current_task = None
                                quantum_slice = 0

                            # Preempção de SRTF, PRIOP, PRIOD
                            if algorithm in ['srtf', 'priop', 'priod'] and current_task and ready_queue:
                                best_candidate_item = ready_queue[0] # Peek
                                current_task_item = make_heap_item(current_task)
                                # Se o melhor candidato na fila for estritamente melhor que a tarefa atual, preempte
                                if best_candidate_item < current_task_item:
                                    heapq.heappush(ready_queue, current_task_item)
                                    current_task = None

                            # 4. DECISÃO DE ESCALONAR NOVA TAREFA
                            if current_task is None and ready_queue:
                                if is_priority_based:
                                    _, _, _, task_to_run = heapq.heappop(ready_queue)
                                    current_task = task_to_run
                                else: # FCFS ou RR
                                    current_task = ready_queue.popleft()
                                
                                # Reseta o quantum e a prioridade dinâmica ao iniciar a execução
                                quantum_slice = 0
                                if algorithm == 'priod':
                                    current_task.priority = current_task.initial_priority
                                if current_task.start_time == -1:
                                    current_task.start_time = current_time

                            # 5. EXECUÇÃO DO CICLO
                            if current_task:
                                timeline.append(current_task.id)
                                current_task.remaining_time -= 1
                                quantum_slice += 1
                            else:
                                timeline.append("-")

                except (socket.error, KeyError, ValueError, ConnectionResetError):
                    if s in inputs: inputs.remove(s)
                    s.close()

    print("Escalonador: Simulação finalizada.")
    while timeline and timeline[-1] == "-":
        timeline.pop()

    output_filename = f"saida_{algorithm}.txt"
    write_output_file(output_filename, timeline, finished_tasks, algorithm)
    generate_gantt_chart(timeline, algorithm)

    for s in inputs:
        s.close()
    
    time.sleep(0.2)
    for port in [CLOCK_PORT, EMITTER_PORT]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
                client_socket.settimeout(0.5)
                client_socket.connect((HOST, port))
                client_socket.sendall(f"END_SIMULATION{MESSAGE_DELIMITER}".encode())
        except Exception:
            pass

# --- PROCESSO PRINCIPAL ---
def main():
    parser = argparse.ArgumentParser(
        prog='python trab-so.py',
        description="Simulador de Escalonamento de Tarefas"
    )
    parser.add_argument("input_file", help="Caminho para o arquivo de descrição de tarefas.")
    parser.add_argument("algorithm", choices=['fcfs', 'rr', 'sjf', 'srtf', 'prioc', 'priop', 'priod'], help="Algoritmo de escalonamento a ser utilizado.")
    args = parser.parse_args()

    scheduler_ready_event = multiprocessing.Event()
    emitter_ready_event = multiprocessing.Event()
    
    scheduler_p = multiprocessing.Process(target=scheduler_process, args=(args.algorithm, scheduler_ready_event))
    emitter_p = multiprocessing.Process(target=emitter_process, args=(args.input_file, emitter_ready_event))
    clock_p = multiprocessing.Process(target=clock_process, args=(scheduler_ready_event, emitter_ready_event))

    print("Iniciando a simulação...")
    scheduler_p.start()
    emitter_p.start()
    clock_p.start()

    scheduler_p.join()
    emitter_p.join()
    clock_p.join()

    print("\nSimulação concluída.")

if __name__ == "__main__":
    main()