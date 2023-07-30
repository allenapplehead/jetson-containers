# cmake_apt

<details open>
<summary><b>CONTAINERS</b></summary>
<br>

| **`cmake:apt`** | |
| :-- | :-- |
| &nbsp;&nbsp;&nbsp;Builds | [![`cmake-apt_jp46`](https://img.shields.io/github/actions/workflow/status/dusty-nv/jetson-containers/cmake-apt_jp46.yml?label=cmake-apt_jp46)](https://github.com/dusty-nv/jetson-containers/actions/workflows/cmake-apt_jp46.yml) [![`cmake-apt_jp51`](https://img.shields.io/github/actions/workflow/status/dusty-nv/jetson-containers/cmake-apt_jp51.yml?label=cmake-apt_jp51)](https://github.com/dusty-nv/jetson-containers/actions/workflows/cmake-apt_jp51.yml) |
| &nbsp;&nbsp;&nbsp;Requires | `L4T >=32.6` |
| &nbsp;&nbsp;&nbsp;Dependencies | [`build-essential`](/packages/build-essential) |
| &nbsp;&nbsp;&nbsp;Dockerfile | [`Dockerfile`](Dockerfile) |
| &nbsp;&nbsp;&nbsp;Notes | upgrade cmake with apt |

</details>

<details open>
<summary><b>RUN CONTAINER</b></summary>
<br>

To start the container, you can use the [`run.sh`](/run.sh)/[`autotag`](/autotag) helpers or manually put together a [`docker run`](https://docs.docker.com/engine/reference/commandline/run/) command:
```bash
# automatically pull or build a compatible container image
./run.sh $(./autotag cmake_apt)

# or if using 'docker run' (specify image and mounts/ect)
sudo docker run --runtime nvidia -it --rm --network=host cmake_apt:35.4.1

```
> <sup>[`run.sh`](/run.sh) forwards arguments to [`docker run`](https://docs.docker.com/engine/reference/commandline/run/) with some defaults added (like `--runtime nvidia`, mounts a `/data` cache, and detects devices)</sup><br>
> <sup>[`autotag`](/autotag) finds a container image that's compatible with your version of JetPack/L4T - either locally, pulled from a registry, or by building it.</sup>

To mount your own directories into the container, use the [`-v`](https://docs.docker.com/engine/reference/commandline/run/#volume) or [`--volume`](https://docs.docker.com/engine/reference/commandline/run/#volume) flags:
```bash
./run.sh -v /path/on/host:/path/in/container $(./autotag cmake_apt)
```
To launch the container running a command, as opposed to an interactive shell:
```bash
./run.sh $(./autotag cmake_apt) my_app --abc xyz
```
You can pass any options to `run.sh` that you would to [`docker run`](https://docs.docker.com/engine/reference/commandline/run/), and it'll print out the full command that it constructs before executing it.
</details>
<details open>
<summary><b>BUILD CONTAINER</b></summary>
<br>

If you use [`autotag`](/autotag) as shown above, it'll ask to build the container for you if needed.  To manually build it, first do this System Setup, then run:
```bash
./build.sh cmake_apt
```
The dependencies from above will be built into the container, and it'll be tested during.  See [`./build.sh --help`](/jetson_containers/build.py) for build options.
</details>