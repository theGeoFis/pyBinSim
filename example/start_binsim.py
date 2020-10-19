import pybinsim

if __name__ == "__main__":

    with pybinsim.BinSim('config/config.cfg') as binsim:
        binsim.stream_start()