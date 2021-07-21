create table stackexchange_db.subscriptions
(
    id serial primary key,
    telegram_id bigint not null,
    site_id integer not null,
    tags jsonb,
    dt_created  timestamp with time zone default current_timestamp
);
alter table stackexchange_db.subscriptions ADD CONSTRAINT fk_subscriptions_to_sites foreign key (site_id) references  stackexchange_db.sites(id);
alter table stackexchange_db.subscriptions owner to stackexchange_bot;