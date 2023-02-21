# Transparent Edge SDN Controller

An SDN Controller for enabling _Transparent Access to Edge Computing Services_.


## Publications

* J. Hammer and H. Hellwagner, _[“Efficient Transparent Access to 5G Edge Services,”](https://ieeexplore.ieee.org/document/9844066)_ in 2022 IEEE 8th Int. Conf. on Network Softwarization (NetSoft), 2022, pp. 91–96.

* J. Hammer, P. Moll, and H. Hellwagner, _[“Transparent Access to 5G Edge Computing Services,”](https://ieeexplore.ieee.org/document/8778343/)_ in 2019 IEEE International Parallel and Distributed Processing Symposium Workshops (IPDPSW), 2019, pp. 895–898.

* D. Kimovski, R. Matha, J. Hammer, N. Mehran, H. Hellwagner, and R. Prodan, _[“Cloud, Fog, or Edge: Where to Compute?,”](https://ieeexplore.ieee.org/document/9321525/)_ IEEE Internet Computing, vol. 25, no. 4, pp. 30–36, 2021.


## Cite this work

If you use this project for your work, please cite the following publication:

_J. Hammer and H. Hellwagner, [“Efficient Transparent Access to 5G Edge Services,”](https://ieeexplore.ieee.org/document/9844066) in 2022 IEEE 8th Int. Conf. on Network Softwarization (NetSoft), 2022, pp. 91–96._

```
@inproceedings{Hammer2022,
author = {Hammer, Josef and Hellwagner, Hermann},
booktitle = {2022 IEEE 8th Int. Conf. Netw. Softwarization},
doi = {10.1109/NetSoft54395.2022.9844066},
isbn = {9781665406949},
pages = {91--96},
publisher = {IEEE},
title = {{Efficient Transparent Access to 5G Edge Services}},
url = {https://ieeexplore.ieee.org/document/9844066},
year = {2022}
}
```


## Dependencies

* [Ryu SDN Framework](https://ryu-sdn.org/)
* [TinyTricia – Space-Optimized Patricia Trie](https://github.com/josefhammer/tinytricia)
* [Docker SDK for Python](https://docker-py.readthedocs.io/)
* [Kubernetes Python Client](https://github.com/kubernetes-client/python)


## Evaluation

The data files used to evaluate this project are expected in `eval/data/`. 
Due to their size, they are stored in a separate repository – [transparent-edge-eval-data](https://github.com/josefhammer/transparent-edge-eval-data).


## More information

See <https://edge.itec.aau.at/> and <https://c3.itec.aau.at/>.


## License

This project is licensed under the [MIT License](LICENSE.md).
