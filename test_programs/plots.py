from matplotlib import pyplot as plt

# Number of clients for each test.
num_clients = [2000, 4000, 6000, 8000]

# Average response time Machine 198
avg_response = [0.1811, 0.3086, 1.7899, 2.8386]
plt.plot(num_clients, avg_response, '--')
plt.plot(num_clients, avg_response, 'ro')
plt.title("Machine 198: Average Response Time")
plt.xlabel("Number of client connections")
plt.ylabel("Response Time (seconds)")
plt.show()

# Average client transmission time Machine 198
avg_client_transmission = [8.8725, 15.1240, 87.7073, 139.0925]
plt.plot(num_clients, avg_client_transmission, '--')
plt.plot(num_clients, avg_client_transmission, 'ro')
plt.title("Machine 198: Average Client Transmission Time")
plt.xlabel("Number of client connections")
plt.ylabel("Average Client Transmission Time (seconds)")
plt.show()

# Total transmission time Machine 198
total_transmission = [9.3228, 15.6219, 95.1074, 155.6741]
plt.plot(num_clients, total_transmission, '--')
plt.plot(num_clients, total_transmission, 'ro')
plt.title("Machine 198: Total Transmission Time")
plt.xlabel("Number of client connections")
plt.ylabel("Total Transmission Time (seconds)")
plt.show()

# Total connection time Machine 198
total_connection = [10.2810, 17.8663, 28.1834, 37.4649]
plt.plot(num_clients, total_connection, '--')
plt.plot(num_clients, total_connection, 'ro')
plt.title("Machine 198: Total Connection Time")
plt.xlabel("Number of client connections")
plt.ylabel("Total Connection Time (seconds)")
plt.show()
