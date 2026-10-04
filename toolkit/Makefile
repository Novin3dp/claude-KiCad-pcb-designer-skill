# build the C core of the negotiated-congestion router (kat/libncr.so)
kat/libncr.so: csrc/ncr.c
	gcc -O3 -shared -fPIC -o $@ $< -lm

demo: kat/libncr.so
	cd examples/demo && ./run_demo.sh

clean:
	rm -f kat/libncr.so
.PHONY: demo clean
