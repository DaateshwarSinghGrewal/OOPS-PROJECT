#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

// Function overloading: same name, distinct parameter lists.
double estimateHours(int minutes) { return minutes / 60.0; }
double estimateHours(double minutes, double breakMinutes) {
    return (minutes - breakMinutes) / 60.0;
}

class Seat {
    int floor_;
    int number_;
public:
    Seat(int floor, int number) : floor_(floor), number_(number) {}
    int number() const { return number_; }
    // Operator overloading: seats compare by floor and number.
    bool operator==(const Seat& other) const {
        return floor_ == other.floor_ && number_ == other.number_;
    }
};

class HasIdentity {
public:
    virtual std::string label() const = 0;
    virtual ~HasIdentity() { std::cout << "Identity interface closed\n"; }
};
class CanReceiveAlerts {
public:
    virtual void notify(const std::string& message) const = 0;
    virtual ~CanReceiveAlerts() = default;
};

// Multiple inheritance combines independent capabilities.
class Student : public HasIdentity, public CanReceiveAlerts {
    std::string name_;
public:
    explicit Student(std::string name) : name_(std::move(name)) {}
    // Virtual function overriding and runtime polymorphism.
    std::string label() const override { return "Student: " + name_; }
    void notify(const std::string& message) const override {
        std::cout << name_ << " — " << message << '\n';
    }
    ~Student() override { std::cout << "Student object released\n"; }
};

// Function template can display several data types.
template <typename T>
void showValue(const std::string& label, const T& value) {
    std::cout << std::left << std::setw(18) << label << value << '\n';
}

int main() {
    try {
        auto* seat = new Seat(0, 27); // Explicit dynamic allocation for the demo.
        std::unique_ptr<Seat> managedSeat(seat);
        Seat requested(0, 27);
        if (!(*managedSeat == requested)) throw std::runtime_error("Seat is unavailable");

        HasIdentity* person = new Student("Aarav");
        CanReceiveAlerts* alerts = dynamic_cast<CanReceiveAlerts*>(person);
        if (!alerts) throw std::runtime_error("Student cannot receive alerts");
        showValue("Account", person->label());
        showValue("Seat number", managedSeat->number());
        showValue("Study hours", estimateHours(120));
        showValue("Net hours", estimateHours(150.0, 30.0));
        alerts->notify("Seat reserved successfully.");

        std::ofstream log("reservation.txt");
        if (!log) throw std::runtime_error("Could not open reservation log");
        log << person->label() << " reserved seat " << managedSeat->number() << '\n';
        log.close();
        std::ifstream input("reservation.txt");
        std::string line;
        std::getline(input, line);
        std::cout << "File record: " << line << '\n';

        delete person; // Virtual destructor calls Student and base destructors.
        // managedSeat's unique_ptr performs delete automatically.
    } catch (const std::exception& error) {
        std::cerr << "Baithak error: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
