DROP DATABASE IF EXISTS hotel_booking_platform;
CREATE DATABASE hotel_booking_platform;
USE hotel_booking_platform;

CREATE TABLE customers (
    customer_id            INT             NOT NULL,
    customer_name           VARCHAR(100)    NOT NULL,
    customer_segment        VARCHAR(20)     NOT NULL,
    customer_signup_date     DATE            NOT NULL,
    customer_home_city       VARCHAR(50)     NOT NULL,
    customer_loyalty_tier    VARCHAR(20)     NOT NULL,

    PRIMARY KEY (customer_id),

    CONSTRAINT chk_customer_segment
        CHECK (customer_segment IN ('Individual', 'Group', 'Corporate')),

    CONSTRAINT chk_loyalty_tier_valid
        CHECK (customer_loyalty_tier IN ('Platinum', 'Gold', 'Silver', 'None'))
);

CREATE TABLE properties (
    property_id            INT             NOT NULL,
    property_name           VARCHAR(100)    NOT NULL,
    property_city            VARCHAR(50)     NOT NULL,
    property_star_rating     TINYINT         NOT NULL,
    property_type            VARCHAR(20)     NOT NULL,
    property_total_rooms     INT             NOT NULL,

    PRIMARY KEY (property_id),

    CONSTRAINT chk_star_rating CHECK (property_star_rating BETWEEN 1 AND 5),
    CONSTRAINT chk_property_type
        CHECK (property_type IN ('Budget', 'Mid-Range', 'Premium', 'Luxury')),
    CONSTRAINT chk_total_rooms CHECK (property_total_rooms > 0),

    CONSTRAINT uq_property_name_city UNIQUE (property_name, property_city)
);

CREATE TABLE bookings (
    booking_id             INT             NOT NULL,
    customer_id            INT             NOT NULL,
    property_id            INT             NOT NULL,
    booking_date            DATE            NOT NULL,
    checkin_date             DATE            NOT NULL,
    checkout_date            DATE            NOT NULL,
    room_type               VARCHAR(20)     NOT NULL,
    num_rooms               INT             NOT NULL,
    nights                  INT             NOT NULL,
    booking_channel          VARCHAR(20)     NOT NULL,
    adr                     DECIMAL(10,2)   NOT NULL,
    discount_amount          DECIMAL(10,2)   NOT NULL DEFAULT 0,
    coupon_code              VARCHAR(20)     NULL,
    total_amount             DECIMAL(12,2)   NOT NULL,
    payment_method           VARCHAR(20)     NOT NULL,
    booking_status           VARCHAR(20)     NOT NULL,

    PRIMARY KEY (booking_id),

    CONSTRAINT fk_bookings_customer
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    CONSTRAINT fk_bookings_property
        FOREIGN KEY (property_id) REFERENCES properties(property_id),

    CONSTRAINT chk_booking_status
        CHECK (booking_status IN ('Completed', 'Cancelled', 'No-Show')),
    CONSTRAINT chk_booking_channel
        CHECK (booking_channel IN ('Direct Website', 'OTA', 'Travel Agent', 'Corporate Portal')),

    CONSTRAINT chk_valid_stay CHECK (checkout_date > checkin_date),

    CONSTRAINT chk_num_rooms_positive CHECK (num_rooms > 0),
    CONSTRAINT chk_nights_positive CHECK (nights > 0),
    CONSTRAINT chk_discount_non_negative CHECK (discount_amount >= 0)

);

CREATE TABLE reviews (
    review_id              INT             NOT NULL AUTO_INCREMENT,
    booking_id             INT             NOT NULL,
    review_rating            DECIMAL(3,1)    NOT NULL,
    review_date              DATE            NOT NULL,

    PRIMARY KEY (review_id),

    CONSTRAINT uq_review_booking UNIQUE (booking_id),
    CONSTRAINT fk_review_booking
        FOREIGN KEY (booking_id) REFERENCES bookings(booking_id),

    CONSTRAINT chk_review_rating_range CHECK (review_rating BETWEEN 1 AND 10)

);

CREATE INDEX idx_bookings_property_status ON bookings (property_id, booking_status);

CREATE INDEX idx_bookings_customer_status_checkin
    ON bookings (customer_id, booking_status, checkin_date);

CREATE INDEX idx_bookings_status ON bookings (booking_status);

CREATE INDEX idx_properties_city ON properties (property_city);

DELIMITER //

CREATE TRIGGER trg_review_status_guard
BEFORE INSERT ON reviews
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(20);
    SELECT booking_status INTO v_status
    FROM bookings WHERE booking_id = NEW.booking_id;

    IF v_status <> 'Completed' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Footnote 5 violation: review on a non-Completed booking';
    END IF;
END//

CREATE TRIGGER trg_booking_temporal_guard
BEFORE INSERT ON bookings
FOR EACH ROW
BEGIN
    DECLARE v_signup DATE;
    SELECT customer_signup_date INTO v_signup
    FROM customers WHERE customer_id = NEW.customer_id;

    IF NEW.booking_date < v_signup THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Footnote 2 violation: booking_date precedes customer_signup_date';
    END IF;
END//

DELIMITER ;

CREATE OR REPLACE VIEW clean_bookings AS
SELECT b.*
FROM bookings b
WHERE b.checkout_date > b.checkin_date
  AND b.num_rooms > 0;

-- Q1
WITH property_revenue AS (
    SELECT
        p.property_id,
        p.property_name,
        p.property_city,
        SUM(b.total_amount) AS revenue
    FROM properties p
    JOIN clean_bookings b
        ON b.property_id = p.property_id
    WHERE b.booking_status = 'Completed'
    GROUP BY p.property_id, p.property_name, p.property_city
),
ranked_revenue AS (
    SELECT
        property_id,
        property_name,
        property_city,
        revenue,
        RANK() OVER (PARTITION BY property_city ORDER BY revenue DESC) AS revenue_rank
    FROM property_revenue
)
SELECT
    property_city,
    property_id,
    property_name,
    revenue
FROM ranked_revenue
WHERE revenue_rank = 1
ORDER BY property_city;

--Q2
WITH completed_with_prev AS (
    SELECT
        customer_id,
        checkin_date,
        LAG(checkin_date) OVER (
            PARTITION BY customer_id
            ORDER BY checkin_date
        ) AS prev_checkin_date
    FROM clean_bookings
    WHERE booking_status = 'Completed'
),
gaps AS (
    SELECT
        customer_id,
        DATEDIFF(checkin_date, prev_checkin_date) AS gap_days
    FROM completed_with_prev
    WHERE prev_checkin_date IS NOT NULL
),
customer_avg_gap AS (
    SELECT
        customer_id,
        AVG(gap_days) AS avg_gap_days
    FROM gaps
    GROUP BY customer_id
)
SELECT COUNT(*) AS customers_with_avg_gap_under_30_days
FROM customer_avg_gap
WHERE avg_gap_days < 30;
