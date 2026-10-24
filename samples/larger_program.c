#include <stdio.h>

/* Compute factorials and print a small report.
   Written to exercise the scanner. */
int factorial(int n) {
    int result = 1;
    for (int i = 2; i <= n; i++) {
        result *= i;          // multiply as we go
    }
    return result;
}

int main() {
    int count = 0;
    float average = 0.0;
    double scale = 1.5e3;
    char letter = 'A';
    char newline = '\n';
    char *title = "Factorial \"report\"";

    while (count < 5 && letter != 'Z') {
        if (count == 3 || count >= 4) {
            average = average + factorial(count) / 2.5;
        } else {
            average -= 1;
        }
        count++;
    }

    printf("%s: %f\n", title, average);
    return 0;
}
